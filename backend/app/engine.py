# Deterministic Decision Engine — NO probabilistic/AI logic allowed
import time
from sqlalchemy.orm import Session
from .models import User
from .schemas import Decision, Reason

DEFAULT_USERS = {
    "S001": "Soham Kotkar",
    "S002": "Vijay Dhawan",
    "S003": "Chandragupta Maurya",
    "S004": "Usman Sheikh",
    "S005": "Manya Sharma",
    "S100": "Admin Test",
}


def seed_db(db: Session):
    """Seed the database with initial users if it's empty."""
    if db.query(User).count() == 0:
        for user_id, name in DEFAULT_USERS.items():
            db_user = User(user_id=user_id, name=name, role="Admin" if user_id == "S100" else "Resident")
            db.add(db_user)
        db.commit()


def is_within_time_window(start_str: str = "07:00", end_str: str = "21:00") -> bool:
    """
    Check if current time falls within the allowed access window (HH:MM format).

    BUG-FIX: The original implementation used a simple string comparison
    (start_str <= current_time <= end_str) which silently fails for windows
    that cross midnight (e.g., 22:00 to 06:00). This version converts to
    minutes-since-midnight for correct arithmetic comparison.
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


def evaluate(db: Session, user_id: str, settings: dict = None) -> tuple[Decision, Reason, str]:
    """
    Deterministic access decision with dynamic settings support.

    BUG-FIX: The original code fetched db_user AFTER the emergency-bypass
    check but still called `db_user.name` at the top before the None check,
    which would raise AttributeError for unknown users in emergency mode.
    Name resolution is now safely guarded before any rule evaluation.
    """
    if settings is None:
        settings = {
            "emergency_mode": False,
            "access_window_start": "07:00",
            "access_window_end": "21:00",
        }

    db_user = db.query(User).filter(User.user_id == user_id).first()
    # Safe name resolution — must happen before any rule that returns name
    name = db_user.name if db_user else "Unknown User"

    # Rule 0: Emergency Bypass — allow all, even unknown users
    if settings.get("emergency_mode", False):
        return Decision.ALLOW, Reason.VALID, f"[EMERGENCY] {name}"

    # Rule 1: User Identity
    if not db_user:
        return Decision.DENY, Reason.UNKNOWN, name

    # Rule 2: Time Window
    start = settings.get("access_window_start", "07:00")
    end = settings.get("access_window_end", "21:00")
    if not is_within_time_window(start, end):
        return Decision.DENY, Reason.TIME_BLOCK, name

    return Decision.ALLOW, Reason.VALID, name
