# Deterministic Decision Engine — NO probabilistic/AI logic allowed
import time
import uuid
from sqlalchemy.orm import Session
from .models import User, Credential, Gate, GateSyncStatus
from .schemas import Decision, Reason

DEFAULT_USERS = {
    "S001": ("Soham Kotkar", 1001, "3280168263", "Resident"),
    "S002": ("Vijay Dhawan", 1002, "3280168264", "Resident"),
    "S003": ("Chandragupta Maurya", 1003, "3280168265", "Resident"),
    "S004": ("Usman Sheikh", 1004, "3280168266", "Resident"),
    "S005": ("Manya Sharma", 1005, "3280168267", "Resident"),
    "S100": ("Admin Test", 1100, "3280168299", "Admin"),
}

DEFAULT_GATES = [
    {
        "gate_id": "GATE_GIRLS_IN",
        "name": "Girls Hostel Main Entrance In",
        "location": "Girls Hostel Block A",
        "direction": "IN",
        "device_ip": "192.168.1.100",
        "device_port": 80,
        "device_model": "COSEC ARGO FACE",
        "device_type": "COSEC"
    },
    {
        "gate_id": "GATE_GIRLS_OUT",
        "name": "Girls Hostel Main Entrance Out",
        "location": "Girls Hostel Block A",
        "direction": "OUT",
        "device_ip": "192.168.1.101",
        "device_port": 80,
        "device_model": "COSEC ARGO FACE",
        "device_type": "COSEC"
    },
    {
        "gate_id": "GATE_DINING_01",
        "name": "Hostel Central Dining Hall Gate",
        "location": "Dining Complex",
        "direction": "IN",
        "device_ip": "192.168.1.102",
        "device_port": 80,
        "device_model": "COSEC PATH CONTROLLER",
        "device_type": "COSEC"
    }
]


def seed_db(db: Session):
    """Seed the database with initial users, credentials, and physical gates if empty."""
    # 1. Seed Gates
    if db.query(Gate).count() == 0:
        for g_data in DEFAULT_GATES:
            gate = Gate(
                gate_id=g_data["gate_id"],
                name=g_data["name"],
                location=g_data["location"],
                direction=g_data["direction"],
                device_ip=g_data["device_ip"],
                device_port=g_data["device_port"],
                device_model=g_data["device_model"],
                device_type=g_data["device_type"],
                is_active=True
            )
            db.add(gate)
        db.commit()

    # 2. Seed Users & Credentials
    if db.query(User).count() == 0:
        gates = db.query(Gate).all()
        for user_id, (name, ref_id, card_no, role) in DEFAULT_USERS.items():
            db_user = User(
                user_id=user_id,
                name=name,
                role=role,
                ref_user_id=ref_id,
                department="Hostel Resident",
                active=True
            )
            db.add(db_user)
            db.flush()

            # Add RFID Credential
            cred = Credential(
                credential_id=str(uuid.uuid4()),
                user_id=user_id,
                type="RFID",
                card_number=card_no,
                status="SYNCED"
            )
            db.add(cred)
            db.flush()

            # Record sync for all gates
            for g in gates:
                sync = GateSyncStatus(
                    id=str(uuid.uuid4()),
                    credential_id=cred.credential_id,
                    gate_id=g.gate_id,
                    status="SYNCED"
                )
                db.add(sync)

        db.commit()


def is_within_time_window(start_str: str = "07:00", end_str: str = "21:00") -> bool:
    """
    Check if current time falls within the allowed access window (HH:MM format).
    Converts to minutes-since-midnight for correct arithmetic comparison.
    """
    def to_minutes(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    now_str = time.strftime("%H:%M")
    now = to_minutes(now_str)
    start = to_minutes(start_str)
    end = to_minutes(end_str)

    if start <= end:
        # Normal window (e.g., 07:00 – 21:00)
        return start <= now <= end
    else:
        # Midnight-crossing window (e.g., 22:00 – 06:00)
        return now >= start or now <= end


def evaluate(db: Session, identifier: str, settings: dict = None) -> tuple[Decision, Reason, str]:
    """
    Deterministic access decision with dynamic settings and multi-format identity resolution.
    Resolves:
    1. Direct User ID (e.g. 'S001')
    2. RFID Card Number (e.g. '3280168263')
    3. COSEC Hardware Numeric Ref ID (e.g. 1001)
    """
    if settings is None:
        settings = {
            "emergency_mode": False,
            "access_window_start": "07:00",
            "access_window_end": "21:00",
        }

    # 1. Direct User ID lookup
    db_user = db.query(User).filter(User.user_id == identifier).first()

    # 2. Credential Card Number lookup
    if not db_user:
        cred = db.query(Credential).filter(Credential.card_number == identifier).first()
        if cred and cred.user:
            db_user = cred.user

    # 3. Numeric Hardware Ref ID lookup
    if not db_user and identifier.isdigit():
        db_user = db.query(User).filter(User.ref_user_id == int(identifier)).first()

    # Safe name resolution
    name = db_user.name if db_user else "Unknown User"

    # Rule 0: Emergency Bypass — allow all, even unknown users
    if settings.get("emergency_mode", False):
        return Decision.ALLOW, Reason.VALID, f"[EMERGENCY] {name}"

    # Rule 1: User Identity
    if not db_user or not getattr(db_user, "active", True):
        return Decision.DENY, Reason.UNKNOWN, name

    # Rule 2: Time Window
    start = settings.get("access_window_start", "07:00")
    end = settings.get("access_window_end", "21:00")
    if not is_within_time_window(start, end):
        return Decision.DENY, Reason.TIME_BLOCK, name

    return Decision.ALLOW, Reason.VALID, name
