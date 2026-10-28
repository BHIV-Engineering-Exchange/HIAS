import asyncio
import time
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.schemas import (
    AccessInput, ControllerEvent, Decision, Reason, Direction, Method,
    ReviewAction, ManualOverrideInput, UserEnrollInput, SettingsUpdateInput,
    GateRegisterInput, GateSyncTriggerInput, CredentialCreateInput
)
from app.engine import evaluate, seed_db
from app.hardware import open_gate, GPIO_ENABLED
from app.logger import log_event
from app.database import engine, Base, get_db
from app.models import User, Credential, Gate, GateSyncStatus, Event, Setting
from app.background import CosecWorker, SyncWorker, resolve_identity

# Initialize Database Schema
Base.metadata.create_all(bind=engine)

app = FastAPI(title="HIAS Controller Core", version="0.3.0")

# Bulletproof CORS Configuration for Girls Hostel onsite local network & cross-origin SSE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
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
SYNC_WORKER: Optional[SyncWorker] = None


@app.on_event("startup")
async def startup_event():
    with next(get_db()) as db:
        seed_db(db)
        # Load settings from DB if they exist
        db_settings = db.query(Setting).all()
        for s in db_settings:
            if s.key == "emergency_mode":
                SYSTEM_SETTINGS[s.key] = s.value == "True"
            else:
                SYSTEM_SETTINGS[s.key] = s.value

    # Initialize COSEC Background Worker & Sync Engine
    global COSEC_WORKER, SYNC_WORKER
    SYNC_WORKER = SyncWorker(get_db)
    COSEC_WORKER = CosecWorker(process_access_request, broadcast_event)
    asyncio.create_task(COSEC_WORKER.start())


@app.on_event("shutdown")
async def shutdown_event():
    if COSEC_WORKER:
        await COSEC_WORKER.stop()


async def broadcast_event(event: ControllerEvent):
    """Push event to all connected SSE clients."""
    data = event.model_dump_json()
    for queue in list(SSE_CLIENTS):
        try:
            await queue.put(data)
        except Exception:
            pass


def process_access_request(
    db: Session,
    user_id: str,
    method: Method,
    device_id: str,
    bypass_cache: bool = False
) -> Optional[ControllerEvent]:
    """Core logic for processing access requests from any gate or reader."""
    # 1. Duplicate Prevention
    if not bypass_cache:
        now = time.monotonic()
        dup_key = (user_id, device_id)
        if dup_key in DUPLICATE_CACHE:
            if now - DUPLICATE_CACHE[dup_key] < DUPLICATE_THRESHOLD:
                return None
        DUPLICATE_CACHE[dup_key] = now

    # 2. Enrichment & Deterministic Decision
    decision, reason, name = evaluate(db, user_id, SYSTEM_SETTINGS)

    # 3. Infer Direction from device_id or Gate registry
    direction = Direction.IN if "in" in device_id.lower() else Direction.OUT
    gate = db.query(Gate).filter(Gate.gate_id == device_id).first()
    if gate and gate.direction:
        direction = Direction.IN if gate.direction.upper() == "IN" else Direction.OUT

    # Resolve canonical user_id if RFID card number was passed
    cred = db.query(Credential).filter(Credential.card_number == user_id).first()
    canonical_user_id = cred.user_id if cred else user_id

    # 4. Build Canonical Event
    event = ControllerEvent(
        user_id=canonical_user_id,
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

    # 6. Save to Central Database
    db_event = Event(
        trace_id=event.trace_id,
        user_id=event.user_id if event.user_id != "UNKNOWN" else None,
        name=event.name,
        direction=event.direction,
        method=event.method,
        decision=event.decision,
        reason=str(event.reason),
        device_id=event.device_id,
        timestamp=datetime.fromisoformat(event.timestamp)
    )
    db.add(db_event)
    db.commit()

    return event


# ---------------------------------------------------------------------------
# Core Health & Status
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    gate_count = db.query(Gate).count()
    cred_count = db.query(Credential).count()
    return {
        "status": "healthy",
        "service": "hias-controller",
        "timestamp": datetime.now().isoformat(),
        "database": "connected",
        "metrics": {
            "total_users": user_count,
            "registered_gates": gate_count,
            "credentials": cred_count
        }
    }


# ---------------------------------------------------------------------------
# Real-Time SSE Stream with Heartbeat Keep-Alive
# ---------------------------------------------------------------------------

@app.get("/events/stream")
async def event_stream(request: Request):
    queue = asyncio.Queue()
    SSE_CLIENTS.append(queue)

    async def event_generator():
        try:
            # Immediate connection acknowledgement
            yield 'event: ping\ndata: {"status":"connected"}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment prevents proxy drops
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in SSE_CLIENTS:
                SSE_CLIENTS.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


# ---------------------------------------------------------------------------
# Access Event Pipeline
# ---------------------------------------------------------------------------

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
            user_id=e.user_id or "UNKNOWN",
            name=e.name or "Unknown User",
            direction=Direction(e.direction) if e.direction else Direction.IN,
            method=Method(e.method) if e.method else Method.RFID,
            decision=Decision(e.decision) if e.decision else Decision.DENY,
            reason=e.reason or Reason.VALID,
            device_id=e.device_id or "unknown",
            timestamp=e.timestamp.isoformat() if e.timestamp else datetime.now().isoformat()
        ) for e in db_events
    ]


# ---------------------------------------------------------------------------
# Identity & One-Click Enrollment API
# ---------------------------------------------------------------------------

@app.get("/users")
async def get_all_users(db: Session = Depends(get_db)):
    db_users = db.query(User).all()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "role": u.role,
            "ref_user_id": u.ref_user_id,
            "department": u.department,
            "active": u.active,
            "credentials": [
                {
                    "credential_id": c.credential_id,
                    "type": c.type,
                    "card_number": c.card_number,
                    "status": c.status
                } for c in u.credentials
            ]
        } for u in db_users
    ]


@app.post("/users")
async def enroll_user(user: UserEnrollInput, db: Session = Depends(get_db)):
    """Standard user creation endpoint (backward compatible)."""
    if db.query(User).filter(User.user_id == user.user_id).first():
        raise HTTPException(status_code=400, detail="User ID already exists")

    ref_id = user.ref_user_id
    if not ref_id:
        max_ref = db.query(func.max(User.ref_user_id)).scalar() or 1000
        ref_id = max_ref + 1

    db_user = User(
        user_id=user.user_id,
        name=user.name,
        role=user.role,
        ref_user_id=ref_id,
        department=user.department or "Hostel Resident"
    )
    db.add(db_user)
    db.commit()
    return {"status": "success", "user_id": user.user_id}


@app.post("/users/enroll")
async def enroll_user_one_click(user_in: UserEnrollInput, db: Session = Depends(get_db)):
    """
    Outcome 2: One-Click Central Enrollment Flow.
    Creates canonical User identity, creates RFID/Face Credential,
    registers sync across all physical hostel gates, and pushes provisioning.
    """
    # 1. Duplicate check on User ID
    if db.query(User).filter(User.user_id == user_in.user_id).first():
        raise HTTPException(status_code=400, detail="User ID already exists")

    # 2. Duplicate check on RFID Card
    if user_in.rfid_card:
        existing_card = db.query(Credential).filter(Credential.card_number == user_in.rfid_card).first()
        if existing_card:
            raise HTTPException(
                status_code=409,
                detail=f"RFID card {user_in.rfid_card} is already assigned to user {existing_card.user_id}"
            )

    # 3. Reference ID allocation
    ref_id = user_in.ref_user_id
    if not ref_id:
        max_ref = db.query(func.max(User.ref_user_id)).scalar() or 1000
        ref_id = max_ref + 1

    # 4. Save canonical user record
    new_user = User(
        user_id=user_in.user_id,
        name=user_in.name,
        role=user_in.role,
        ref_user_id=ref_id,
        department=user_in.department or "Hostel Resident",
        active=True
    )
    db.add(new_user)
    db.flush()

    # 5. Create Credentials
    created_creds = []
    if user_in.rfid_card:
        rfid_cred = Credential(
            credential_id=str(uuid.uuid4()),
            user_id=new_user.user_id,
            type="RFID",
            card_number=user_in.rfid_card,
            status="PENDING"
        )
        db.add(rfid_cred)
        created_creds.append(rfid_cred)

    if user_in.face_data:
        face_cred = Credential(
            credential_id=str(uuid.uuid4()),
            user_id=new_user.user_id,
            type="FACE",
            face_data=user_in.face_data,
            status="PENDING"
        )
        db.add(face_cred)
        created_creds.append(face_cred)

    # If no credential given, create default RFID credential placeholder
    if not created_creds:
        rfid_cred = Credential(
            credential_id=str(uuid.uuid4()),
            user_id=new_user.user_id,
            type="RFID",
            card_number=f"328016{ref_id:04d}",
            status="PENDING"
        )
        db.add(rfid_cred)
        created_creds.append(rfid_cred)

    # 6. Associate with all active registered gates
    gates = db.query(Gate).filter(Gate.is_active == True).all()
    for cred in created_creds:
        for gate in gates:
            sync_entry = GateSyncStatus(
                id=str(uuid.uuid4()),
                credential_id=cred.credential_id,
                gate_id=gate.gate_id,
                status="PENDING"
            )
            db.add(sync_entry)

    db.commit()

    # 7. Drive Synchronization
    sync_report = {}
    if user_in.auto_sync:
        sync_worker = SyncWorker(get_db)
        sync_report = await sync_worker.sync_user_to_all_gates(new_user.user_id)

    return {
        "status": "success",
        "user_id": new_user.user_id,
        "name": new_user.name,
        "ref_user_id": new_user.ref_user_id,
        "role": new_user.role,
        "credentials": [
            {"credential_id": c.credential_id, "type": c.type, "card_number": c.card_number}
            for c in created_creds
        ],
        "sync_report": sync_report
    }


@app.get("/users/search")
async def search_users(q: str = "", db: Session = Depends(get_db)):
    q_str = f"%{q}%"
    db_users = db.query(User).filter(
        (User.user_id.ilike(q_str)) | (User.name.ilike(q_str))
    ).limit(20).all()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "role": u.role,
            "ref_user_id": u.ref_user_id,
            "credentials": [
                {"type": c.type, "card_number": c.card_number, "status": c.status}
                for c in u.credentials
            ]
        } for u in db_users
    ]


@app.get("/users/{user_id}/credentials")
async def get_user_credentials(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return [
        {
            "credential_id": c.credential_id,
            "type": c.type,
            "card_number": c.card_number,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None
        } for c in user.credentials
    ]


@app.post("/users/{user_id}/credentials")
async def add_user_credential(user_id: str, cred_in: CredentialCreateInput, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if cred_in.type == "RFID" and cred_in.card_number:
        dup = db.query(Credential).filter(Credential.card_number == cred_in.card_number).first()
        if dup:
            raise HTTPException(status_code=409, detail=f"Card number {cred_in.card_number} already in use")

    cred = Credential(
        credential_id=str(uuid.uuid4()),
        user_id=user_id,
        type=cred_in.type.value,
        card_number=cred_in.card_number,
        face_data=cred_in.face_data,
        status="PENDING"
    )
    db.add(cred)

    # Add sync status for gates
    gates = db.query(Gate).filter(Gate.is_active == True).all()
    for g in gates:
        db.add(GateSyncStatus(
            id=str(uuid.uuid4()),
            credential_id=cred.credential_id,
            gate_id=g.gate_id,
            status="PENDING"
        ))
    db.commit()

    # Sync
    sync_worker = SyncWorker(get_db)
    await sync_worker.sync_user_to_all_gates(user_id)

    return {"status": "success", "credential_id": cred.credential_id}


# ---------------------------------------------------------------------------
# Gate & Terminal Registry
# ---------------------------------------------------------------------------

@app.get("/gates")
async def list_gates(db: Session = Depends(get_db)):
    gates = db.query(Gate).all()
    res = []
    for g in gates:
        synced_count = db.query(GateSyncStatus).filter(
            GateSyncStatus.gate_id == g.gate_id,
            GateSyncStatus.status == "SYNCED"
        ).count()
        pending_count = db.query(GateSyncStatus).filter(
            GateSyncStatus.gate_id == g.gate_id,
            GateSyncStatus.status.in_(["PENDING", "RETRYING", "FAILED"])
        ).count()
        res.append({
            "gate_id": g.gate_id,
            "name": g.name,
            "location": g.location,
            "direction": g.direction,
            "device_ip": g.device_ip,
            "device_port": g.device_port,
            "device_model": g.device_model,
            "device_type": g.device_type,
            "is_active": g.is_active,
            "synced_credentials": synced_count,
            "pending_credentials": pending_count
        })
    return res


@app.post("/gates")
async def register_gate(gate_in: GateRegisterInput, db: Session = Depends(get_db)):
    if db.query(Gate).filter(Gate.gate_id == gate_in.gate_id).first():
        raise HTTPException(status_code=400, detail="Gate ID already exists")

    gate = Gate(
        gate_id=gate_in.gate_id,
        name=gate_in.name,
        location=gate_in.location,
        direction=gate_in.direction.value,
        device_ip=gate_in.device_ip,
        device_port=gate_in.device_port,
        device_model=gate_in.device_model,
        device_type=gate_in.device_type,
        is_active=gate_in.is_active
    )
    db.add(gate)
    db.commit()
    return {"status": "success", "gate_id": gate.gate_id}


@app.post("/gates/{gate_id}/sync")
async def trigger_gate_resync(gate_id: str, db: Session = Depends(get_db)):
    gate = db.query(Gate).filter(Gate.gate_id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    sync_worker = SyncWorker(get_db)
    # Mark all credentials for this gate as PENDING and sync
    db.query(GateSyncStatus).filter(GateSyncStatus.gate_id == gate_id).update({"status": "PENDING"})
    db.commit()

    report = await sync_worker.retry_failed_syncs()
    return {"status": "sync_triggered", "gate_id": gate_id, "report": report}


# ---------------------------------------------------------------------------
# Sync Engine Management Endpoints
# ---------------------------------------------------------------------------

@app.get("/sync/status")
async def get_sync_status(db: Session = Depends(get_db)):
    total_syncs = db.query(GateSyncStatus).count()
    synced = db.query(GateSyncStatus).filter(GateSyncStatus.status == "SYNCED").count()
    pending = db.query(GateSyncStatus).filter(GateSyncStatus.status == "PENDING").count()
    retrying = db.query(GateSyncStatus).filter(GateSyncStatus.status == "RETRYING").count()
    failed = db.query(GateSyncStatus).filter(GateSyncStatus.status == "FAILED").count()

    recent_failures = db.query(GateSyncStatus).filter(
        GateSyncStatus.status.in_(["RETRYING", "FAILED"])
    ).limit(10).all()

    return {
        "summary": {
            "total_records": total_syncs,
            "synced": synced,
            "pending": pending,
            "retrying": retrying,
            "failed": failed,
            "sync_health": f"{(synced / max(total_syncs, 1)) * 100:.1f}%"
        },
        "recent_issues": [
            {
                "gate_id": f.gate_id,
                "credential_id": f.credential_id,
                "retry_count": f.retry_count,
                "last_error": f.last_error
            } for f in recent_failures
        ]
    }


@app.post("/sync/retry")
async def trigger_sync_retry():
    sync_worker = SyncWorker(get_db)
    report = await sync_worker.retry_failed_syncs()
    return {"status": "completed", "report": report}


# ---------------------------------------------------------------------------
# Settings & Overrides
# ---------------------------------------------------------------------------

@app.get("/settings")
async def get_settings():
    return SYSTEM_SETTINGS


@app.post("/settings")
async def update_settings(new_settings: SettingsUpdateInput, db: Session = Depends(get_db)):
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


@app.post("/manual/override", response_model=ControllerEvent)
async def manual_override(payload: ManualOverrideInput, db: Session = Depends(get_db)):
    reason_text = payload.reason
    event = process_access_request(db, "S100", Method.MANUAL, "manual_console_01", bypass_cache=True)
    if event:
        event.reason = reason_text
        db_event = db.query(Event).filter(Event.trace_id == event.trace_id).first()
        if db_event:
            db_event.reason = reason_text
            db.commit()
        await broadcast_event(event)
    return event


@app.get("/system/devices")
async def get_system_devices(db: Session = Depends(get_db)):
    gates = db.query(Gate).all()
    devices = [
        {"name": "HIAS Controller Core", "status": "Healthy", "uptime": "99.98%", "latency": "2ms", "type": "software"},
        {"name": "Central SQLite/PostgreSQL Database", "status": "Healthy", "uptime": "100%", "latency": "3ms", "type": "software"},
        {"name": "Relay Control Unit", "status": "Healthy" if GPIO_ENABLED else "Simulated", "uptime": "99.90%", "latency": "1ms", "type": "hardware"}
    ]
    for g in gates:
        devices.append({
            "name": f"{g.name} ({g.device_model})",
            "status": "Online" if g.is_active else "Offline",
            "uptime": "99.95%",
            "latency": "8ms" if g.device_type == "COSEC" else "1ms",
            "type": "hardware"
        })
    return devices


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

    db_event = db.query(Event).filter(Event.trace_id == event.trace_id).first()
    if db_event:
        db_event.decision = event.decision
        db_event.reason = event.reason
        db.commit()
    else:
        db_event = Event(
            trace_id=event.trace_id,
            user_id=event.user_id,
            name=event.name,
            direction=event.direction,
            method=event.method,
            decision=event.decision,
            reason=str(event.reason),
            device_id=event.device_id,
            timestamp=datetime.fromisoformat(event.timestamp)
        )
        db.add(db_event)
        db.commit()

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
    hours = [e.timestamp.hour for e in db_events if e.timestamp]
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
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hias_access_logs.csv"}
    )


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
                "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.now().isoformat()
            })
        elif event.method == Method.MANUAL:
            alerts.append({
                "id": event.trace_id,
                "type": "System",
                "message": f"Manual Override Triggered at {event.device_id}",
                "severity": "Medium",
                "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.now().isoformat()
            })
    if not GPIO_ENABLED:
        alerts.append({
            "id": "h-001",
            "type": "Hardware",
            "message": "GPIO Not Detected: Simulated Mode",
            "severity": "Low",
            "timestamp": datetime.now().isoformat()
        })
    return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)


@app.post("/alerts/clear")
async def clear_alerts(db: Session = Depends(get_db)):
    db.query(Event).delete()
    db.commit()
    return {"status": "success"}


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
