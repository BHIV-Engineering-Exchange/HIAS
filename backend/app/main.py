import asyncio
import time
import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.schemas import (
    AccessInput, ControllerEvent, Decision, Reason, Direction, Method,
    ReviewAction, ManualOverrideInput, UserEnrollInput, SettingsUpdateInput
)
from app.engine import evaluate, seed_db
from app.hardware import open_gate, GPIO_ENABLED
from app.logger import log_event
from app.database import engine, Base, get_db
from app.models import User, Event, Setting
from app.background import CosecWorker

# Initialize Database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="HIAS Controller Core", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global State ---
SSE_CLIENTS: List[asyncio.Queue] = []
DUPLICATE_CACHE = {}  # (user_id, device_id) -> timestamp
DUPLICATE_THRESHOLD = 2.0
REVIEW_QUEUE = {}  # trace_id -> ControllerEvent

# Default Settings (will be overridden by DB if exists)
SYSTEM_SETTINGS = {
    "emergency_mode": False,
    "access_window_start": "07:00",
    "access_window_end": "21:00",
    "require_admin_approval": False
}

COSEC_WORKER: Optional[CosecWorker] = None

@app.on_event("startup")
async def startup_event():
    # BUG-FIX: must be async def to safely call asyncio.create_task
    with next(get_db()) as db:
        seed_db(db)
        # Load settings from DB if they exist
        db_settings = db.query(Setting).all()
        for s in db_settings:
            # Simple parsing: assume boolean for emergency_mode
            if s.key == "emergency_mode":
                SYSTEM_SETTINGS[s.key] = s.value == "True"
            else:
                SYSTEM_SETTINGS[s.key] = s.value

    # Initialize COSEC Background Worker
    global COSEC_WORKER
    COSEC_WORKER = CosecWorker(process_access_request, broadcast_event)
    asyncio.create_task(COSEC_WORKER.start())

@app.on_event("shutdown")
async def shutdown_event():
    if COSEC_WORKER:
        await COSEC_WORKER.stop()

async def broadcast_event(event: ControllerEvent):
    """Push event to all connected SSE clients."""
    data = event.model_dump_json()
    for queue in SSE_CLIENTS:
        await queue.put(data)

def process_access_request(db: Session, user_id: str, method: Method, device_id: str, bypass_cache: bool = False) -> Optional[ControllerEvent]:
    """Core logic for processing access requests from any source."""
    # 1. Duplicate Prevention
    # BUG-FIX: asyncio.get_event_loop().time() is unsafe in a sync function running
    # inside an async FastAPI server. Use time.monotonic() which is always safe.
    if not bypass_cache:
        now = time.monotonic()
        dup_key = (user_id, device_id)
        if dup_key in DUPLICATE_CACHE:
            if now - DUPLICATE_CACHE[dup_key] < DUPLICATE_THRESHOLD:
                return None
        DUPLICATE_CACHE[dup_key] = now

    # 2. Enrichment & Decision
    decision, reason, name = evaluate(db, user_id, SYSTEM_SETTINGS)

    # 3. Infer Direction from device_id
    direction = Direction.IN if "in" in device_id.lower() else Direction.OUT

    # 4. Build Canonical Event
    event = ControllerEvent(
        user_id=user_id,
        name=name,
        direction=direction,
        method=method,
        decision=decision,
        reason=reason,
        device_id=device_id
    )

    # 5. Trigger Hardware if ALLOWed
    if decision == Decision.ALLOW:
        open_gate(event.trace_id, event.user_id, device_id)

    # 6. Save to DB
    db_event = Event(
        trace_id=event.trace_id,
        user_id=event.user_id,
        name=event.name,
        direction=event.direction,
        method=event.method,
        decision=event.decision,
        reason=event.reason,
        device_id=event.device_id,
        timestamp=datetime.fromisoformat(event.timestamp)
    )
    db.add(db_event)
    db.commit()

    return event

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "hias-controller"}

@app.post("/access/event", response_model=ControllerEvent)
async def access_event(payload: AccessInput, db: Session = Depends(get_db)):
    event = process_access_request(db, payload.user_id, payload.method, payload.device_id)
    if not event:
        raise HTTPException(status_code=429, detail="Duplicate scan ignored")
    await broadcast_event(event)
    return event

@app.get("/events")
async def get_events(limit: int = 10, db: Session = Depends(get_db)):
    db_events = db.query(Event).order_by(Event.timestamp.desc()).limit(limit).all()
    return [
        ControllerEvent(
            trace_id=e.trace_id,
            user_id=e.user_id,
            name=e.name,
            direction=e.direction,
            method=e.method,
            decision=e.decision,
            reason=e.reason,
            device_id=e.device_id,
            timestamp=e.timestamp.isoformat()
        ) for e in db_events
    ]

@app.get("/events/stream")
async def event_stream(request: Request):
    queue = asyncio.Queue()
    SSE_CLIENTS.append(queue)
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            SSE_CLIENTS.remove(queue)
    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/manual/override", response_model=ControllerEvent)
async def manual_override(payload: ManualOverrideInput, db: Session = Depends(get_db)):
    # BUG-FIX: replaced raw dict with strict Pydantic ManualOverrideInput model
    reason_text = payload.reason
    # Use bypass_cache=True for manual overrides
    event = process_access_request(db, "S100", Method.MANUAL, "manual_console_01", bypass_cache=True)
    if event:
        event.reason = reason_text
        # Update the reason in DB too
        db_event = db.query(Event).filter(Event.trace_id == event.trace_id).first()
        if db_event:
            db_event.reason = reason_text
            db.commit()
        await broadcast_event(event)
    return event

@app.get("/settings")
async def get_settings():
    return SYSTEM_SETTINGS

@app.post("/settings")
async def update_settings(new_settings: SettingsUpdateInput, db: Session = Depends(get_db)):
    # BUG-FIX: replaced raw dict with strict Pydantic SettingsUpdateInput model
    global SYSTEM_SETTINGS
    update_data = new_settings.model_dump(exclude_none=True)
    SYSTEM_SETTINGS.update(update_data)
    for key, value in update_data.items():
        db_setting = db.query(Setting).filter(Setting.key == key).first()
        if db_setting:
            db_setting.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
    db.commit()
    return SYSTEM_SETTINGS

@app.get("/system/devices")
async def get_system_devices():
    return [
        {"name": "HIAS Controller Core", "status": "Healthy", "uptime": "99.98%", "latency": "2ms", "type": "software"},
        {"name": "PostgreSQL Database", "status": "Healthy", "uptime": "100%", "latency": "5ms", "type": "software"},
        {"name": "Face Recognition Node", "status": "Healthy", "uptime": "99.95%", "latency": "156ms", "type": "hardware"},
        {"name": "RFID Reader Grid", "status": "Healthy", "uptime": "99.99%", "latency": "8ms", "type": "hardware"},
        {"name": "Relay Control Unit", "status": "Healthy" if GPIO_ENABLED else "Simulated", "uptime": "99.90%", "latency": "1ms", "type": "hardware"}
    ]

@app.get("/review/queue")
async def get_review_queue():
    return list(REVIEW_QUEUE.values())

@app.post("/review/action")
async def process_review_action(data: ReviewAction, db: Session = Depends(get_db)):
    if data.trace_id not in REVIEW_QUEUE:
        raise HTTPException(status_code=404, detail="Event not found in queue")
    event = REVIEW_QUEUE.pop(data.trace_id)
    if data.action == "confirm":
        event.decision = Decision.ALLOW
        open_gate(event.trace_id, event.user_id, event.device_id)
    else:
        event.decision = Decision.DENY
    # Update existing event in DB
    db_event = db.query(Event).filter(Event.trace_id == event.trace_id).first()
    if db_event:
        db_event.decision = event.decision
        db_event.reason = event.reason
        db.commit()
    else:
        # Fallback if not found (shouldn't happen)
        db_event = Event(
            trace_id=event.trace_id,
            user_id=event.user_id,
            name=event.name,
            direction=event.direction,
            method=event.method,
            decision=event.decision,
            reason=event.reason,
            device_id=event.device_id,
            timestamp=datetime.fromisoformat(event.timestamp)
        )
        db.add(db_event)
        db.commit()
    
    # Broadcast the decision to the live feed
    await broadcast_event(event)
    
    return {"status": "success", "decision": event.decision}

@app.post("/simulate/review")
async def simulate_review_event(db: Session = Depends(get_db)):
    event = process_access_request(db, "S002", Method.FACE, "cam_01")
    if event:
        event.decision = Decision.REVIEW
        event.reason = Reason.UNKNOWN
        REVIEW_QUEUE[event.trace_id] = event
        await broadcast_event(event)
    return event

@app.get("/reports/stats")
async def get_report_stats(db: Session = Depends(get_db)):
    from collections import Counter
    db_events = db.query(Event).all()
    hours = [e.timestamp.hour for e in db_events]
    hour_counts = Counter(hours)
    decisions = Counter([e.decision for e in db_events])
    methods = Counter([e.method for e in db_events])
    return {
        "hourly_distribution": [hour_counts.get(i, 0) for i in range(24)],
        "decision_split": {
            "allowed": decisions.get(Decision.ALLOW, 0),
            "denied": decisions.get(Decision.DENY, 0)
        },
        "method_split": {
            "rfid": methods.get(Method.RFID, 0),
            "face": methods.get(Method.FACE, 0),
            "manual": methods.get(Method.MANUAL, 0)
        }
    }

@app.get("/reports/export")
async def export_logs_csv(db: Session = Depends(get_db)):
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "User ID", "Name", "Method", "Decision", "Reason", "Device ID"])
    db_events = db.query(Event).order_by(Event.timestamp.desc()).all()
    for e in db_events:
        writer.writerow([e.timestamp, e.user_id, e.name, e.method, e.decision, e.reason, e.device_id])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=hias_access_logs.csv"})

@app.get("/alerts")
async def get_alerts(db: Session = Depends(get_db)):
    alerts = []
    db_events = db.query(Event).order_by(Event.timestamp.desc()).limit(20).all()
    for event in db_events:
        if event.decision == Decision.DENY:
            alerts.append({
                "id": event.trace_id,
                "type": "Security",
                "message": f"Unauthorized Access Attempt: {event.name} ({event.user_id})",
                "severity": "High",
                "timestamp": event.timestamp.isoformat()
            })
        elif event.method == Method.MANUAL:
             alerts.append({
                "id": event.trace_id,
                "type": "System",
                "message": f"Manual Override Triggered at {event.device_id}",
                "severity": "Medium",
                "timestamp": event.timestamp.isoformat()
            })
    if not GPIO_ENABLED:
        alerts.append({
            "id": "h-001", "type": "Hardware", "message": "GPIO Not Detected: Simulated Mode",
            "severity": "Low", "timestamp": datetime.now().isoformat()
        })
    return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)

@app.post("/alerts/clear")
async def clear_alerts(db: Session = Depends(get_db)):
    """Clears all events from the database (effectively clearing alerts)."""
    db.query(Event).delete()
    db.commit()
    return {"status": "success"}

@app.get("/users")
async def get_all_users(db: Session = Depends(get_db)):
    db_users = db.query(User).all()
    return [{"user_id": u.user_id, "name": u.name, "role": u.role} for u in db_users]

@app.post("/users")
async def enroll_user(user: UserEnrollInput, db: Session = Depends(get_db)):
    # BUG-FIX: replaced raw dict with strict Pydantic UserEnrollInput model
    if db.query(User).filter(User.user_id == user.user_id).first():
        raise HTTPException(status_code=400, detail="User ID already exists")
    db.add(User(user_id=user.user_id, name=user.name, role=user.role))
    db.commit()
    return {"status": "success", "user_id": user.user_id}

@app.get("/users/search")
async def search_users(q: str = "", db: Session = Depends(get_db)):
    q = f"%{q}%"
    db_users = db.query(User).filter((User.user_id.ilike(q)) | (User.name.ilike(q))).limit(10).all()
    return [{"user_id": u.user_id, "name": u.name, "role": u.role} for u in db_users]

@app.get("/stats/summary")
async def get_stats_summary(db: Session = Depends(get_db)):
    total = db.query(Event).count()
    granted = db.query(Event).filter(Event.decision == Decision.ALLOW).count()
    denied = total - granted
    overrides = db.query(Event).filter(Event.method == Method.MANUAL).count()
    return {"total": total, "granted": granted, "denied": denied, "overrides": overrides}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
