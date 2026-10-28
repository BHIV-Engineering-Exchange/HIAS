from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import Response, JSONResponse
import time
from typing import Optional

app = FastAPI(title="COSEC Matrix Device Simulator")

# Device state
IS_ONLINE = True
USERS = {
    "12": {"user_id": "12", "name": "Soham Kotkar", "card1": "3280168263"},
    "15": {"user_id": "15", "name": "Vijay Dhawan", "card1": "3280168264"},
    "101": {"user_id": "101", "name": "Admin Test", "card1": "3280168299"}
}
CREDENTIALS = {}

# In-memory event store
EVENTS = [
    {"index": 101, "userid": "12", "timestamp": "2026-10-28 10:30:01", "type": "face", "detail3": 64},
    {"index": 102, "userid": "15", "timestamp": "2026-10-28 10:35:10", "type": "rfid", "detail3": 258},
]


@app.middleware("http")
async def check_online_middleware(request: Request, call_next):
    if not IS_ONLINE and not request.url.path.startswith("/simulate"):
        return JSONResponse(status_code=503, content={"error": "Device Offline"})
    return await call_next(request)


@app.get("/device.cgi/check-enrollment")
async def check_enrollment():
    return Response(content="Response-Code=0", media_type="text/plain")


@app.get("/device.cgi/device-basic-config")
async def device_basic_config(action: str = "get"):
    if action == "get":
        return Response(content="app=1 name=Hostel-Terminal-Argo max-fingers=2 finger-format=0", media_type="text/plain")
    return Response(content="Response-Code=0", media_type="text/plain")


@app.get("/device.cgi/users")
async def handle_users(
    action: str = Query(...),
    user_id: Optional[str] = Query(None, alias="user-id"),
    ref_user_id: Optional[str] = Query(None, alias="ref-user-id"),
    name: Optional[str] = None,
    card1: Optional[str] = None,
    enable_fr: Optional[str] = Query(None, alias="enable-fr")
):
    if action == "set":
        USERS[user_id] = {
            "user_id": user_id,
            "ref_user_id": ref_user_id,
            "name": name,
            "card1": card1,
            "enable_fr": enable_fr
        }
        return Response(content="Response-Code=0", media_type="text/plain")
    elif action == "delete":
        USERS.pop(user_id, None)
        return Response(content="Response-Code=0", media_type="text/plain")
    elif action == "get":
        u = USERS.get(user_id, {})
        return Response(
            content=f"user-id={user_id} ref-user-id={u.get('ref_user_id', '1')} name={u.get('name', 'Resident')} user-active=1 card1={u.get('card1', '0')}",
            media_type="text/plain"
        )
    raise HTTPException(status_code=400, detail="Invalid action")


@app.api_route("/device.cgi/credential", methods=["GET", "POST"])
async def handle_credential(
    request: Request,
    action: str = Query(...),
    type: Optional[str] = None,
    user_id: Optional[str] = Query(None, alias="user-id"),
    card1: Optional[str] = None
):
    if action == "set":
        CREDENTIALS[f"{user_id}_{type}"] = {"card1": card1}
        return Response(content="Response-Code=0", media_type="text/plain")
    elif action == "delete":
        CREDENTIALS.pop(f"{user_id}_{type}", None)
        return Response(content="Response-Code=0", media_type="text/plain")
    return Response(content="Response-Code=0", media_type="text/plain")


@app.get("/device.cgi/command")
async def handle_command(
    action: str = Query(...),
    extra_info1: Optional[str] = Query("HIAS", alias="extra-info1"),
    doorid: str = "1"
):
    if action == "opendoor":
        print(f"[MOCK_DEVICE] Door opened by controller! (extra-info={extra_info1})")
        return Response(content="Response-Code=0", media_type="text/plain")
    elif action == "getusercount":
        return Response(content=f"user-count={len(USERS)}", media_type="text/plain")
    elif action == "geteventcount":
        return Response(
            content=f"<COSEC_API><Roll-over-count>0</Roll-over-count><seq-number>{len(EVENTS)}</seq-number></COSEC_API>",
            media_type="application/xml"
        )
    return Response(content="Response-Code=0", media_type="text/plain")


@app.get("/device.cgi/commands")
async def execute_legacy_command(
    action: str = Query(...),
    cmd: str = Query(...),
    doorid: str = Query("1")
):
    if action == "set" and cmd == "open-door":
        print(f"[MOCK_DEVICE] Door {doorid} opened!")
        return {"status": "success", "message": f"Door {doorid} opened"}
    raise HTTPException(status_code=400, detail="Invalid command")


@app.get("/device.cgi/events")
async def get_events(
    action: str = Query(...),
    index: int = Query(0),
    seq_number: Optional[int] = Query(None, alias="seq-number"),
    format: str = "xml",
    delay: float = Query(0.0),
    fail: bool = Query(False)
):
    if fail:
        raise HTTPException(status_code=500, detail="Internal Device Error")
    if delay > 0:
        time.sleep(delay)

    start_index = seq_number if seq_number is not None else index
    new_events = [e for e in EVENTS if e["index"] > start_index]

    if action == "getevent":
        # Official Matrix COSEC XML format
        xml_output = "<COSEC_API>"
        for e in new_events:
            xml_output += f"""<Events>
<roll-over-count>0</roll-over-count>
<seq-No>{e["index"]}</seq-No>
<date>28/10/2026</date>
<time>10:30:00</time>
<event-id>101</event-id>
<detail-1>{e["userid"]}</detail-1>
<detail-3>{e.get("detail3", 258)}</detail-3>
</Events>"""
        xml_output += "</COSEC_API>"
        return Response(content=xml_output, media_type="application/xml")
    elif action == "get":
        # Legacy simulator XML format
        xml_output = "<events>"
        for e in new_events:
            xml_output += f'<event index="{e["index"]}" userid="{e["userid"]}" timestamp="{e["timestamp"]}" type="{e["type"]}" />'
        xml_output += "</events>"
        return Response(content=xml_output, media_type="application/xml")

    raise HTTPException(status_code=400, detail="Invalid action")


# Simulation endpoints
@app.post("/simulate/swipe")
async def simulate_swipe(userid: str, type: str = "rfid"):
    new_index = (EVENTS[-1]["index"] + 1) if EVENTS else 100
    detail3 = 64 if type == "face" else 258
    event = {
        "index": new_index,
        "userid": userid,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": type,
        "detail3": detail3
    }
    EVENTS.append(event)
    return event


@app.post("/simulate/offline")
async def simulate_offline():
    global IS_ONLINE
    IS_ONLINE = False
    return {"status": "device_offline"}


@app.post("/simulate/online")
async def simulate_online():
    global IS_ONLINE
    IS_ONLINE = True
    return {"status": "device_online"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
