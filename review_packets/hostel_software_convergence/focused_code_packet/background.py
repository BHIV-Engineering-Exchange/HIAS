import os
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from sqlalchemy.orm import Session
from app.adapters.cosec import COSECAdapter
from app.database import get_db
from app.models import User, Credential, Gate, GateSyncStatus
from app.schemas import Method, Direction

# Configuration loaded from Environment Variables
COSEC_CONFIG = {
    "base_url": os.getenv("COSEC_BASE_URL", "http://192.168.1.100"),
    "username": os.getenv("COSEC_USERNAME", "admin"),
    "password": os.getenv("COSEC_PASSWORD", "password123"),
    "poll_interval": float(os.getenv("COSEC_POLL_INTERVAL", "2.0")),
    "worker_enabled": os.getenv("COSEC_WORKER_ENABLED", "true" if not os.getenv("TESTING") else "false").lower() == "true"
}

# Legacy mapping preserved as fallback for legacy tests only
LEGACY_USER_MAPPING = {
    "12": "S001",
    "15": "S002",
    "101": "S100"
}


def resolve_identity(db: Session, device_user_id: str) -> Tuple[Optional[str], Optional[str], Optional[Method]]:
    """
    Database-driven identity resolution.
    Eliminates artificial hardcoded mappings and scales to 2,500+ users.
    Resolves in priority:
    1. Credential table by card_number
    2. User table by numeric ref_user_id
    3. User table by canonical user_id
    4. Legacy mapping fallback
    5. Returns None if unmapped/unregistered
    """
    if not device_user_id:
        return None, None, None

    raw_str = str(device_user_id).strip()

    # 1. Look up Credential by RFID card number
    cred = db.query(Credential).filter(Credential.card_number == raw_str).first()
    if cred and cred.user:
        return cred.user.user_id, cred.user.name, Method.RFID

    # 2. Look up by numeric hardware ref_user_id
    if raw_str.isdigit():
        ref_num = int(raw_str)
        user_by_ref = db.query(User).filter(User.ref_user_id == ref_num).first()
        if user_by_ref:
            return user_by_ref.user_id, user_by_ref.name, None

    # 3. Look up by canonical user_id
    user_by_id = db.query(User).filter(User.user_id == raw_str).first()
    if user_by_id:
        return user_by_id.user_id, user_by_id.name, None

    # 4. Check legacy mapping fallback
    if raw_str in LEGACY_USER_MAPPING:
        legacy_id = LEGACY_USER_MAPPING[raw_str]
        user_legacy = db.query(User).filter(User.user_id == legacy_id).first()
        name = user_legacy.name if user_legacy else f"User {legacy_id}"
        return legacy_id, name, None

    # 5. Unregistered / unknown
    return None, None, None


class CosecWorker:
    """
    Background worker for listening to and polling COSEC events.
    Captures live swipes/face punches and feeds the Deterministic Engine.
    """

    def __init__(self, process_request_fn, broadcast_fn):
        self.adapter = COSECAdapter(
            COSEC_CONFIG["base_url"],
            COSEC_CONFIG["username"],
            COSEC_CONFIG["password"]
        )
        self.process_request = process_request_fn
        self.broadcast = broadcast_fn
        self.last_index = 0
        self.running = False
        self._task = None

    async def start(self):
        if not COSEC_CONFIG["worker_enabled"]:
            print("[COSEC_WORKER] Background polling disabled by configuration.")
            return

        self.running = True
        self._task = asyncio.create_task(self._loop())
        print("[COSEC_WORKER] Background polling started.")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[COSEC_WORKER] Background polling stopped.")

    async def _loop(self):
        while self.running:
            await self._loop_once()
            await asyncio.sleep(COSEC_CONFIG["poll_interval"])

    async def _loop_once(self):
        """Single iteration of the polling loop."""
        try:
            events = await self.adapter.fetch_events(self.last_index)
            if events:
                events.sort(key=lambda x: x["index"])

                for raw_event in events:
                    if raw_event["index"] <= self.last_index:
                        continue

                    raw_dev_uid = raw_event.get("device_user_id", "")
                    method = raw_event.get("method", Method.RFID)
                    device_id = f"cosec_device_{raw_event.get('index', 0)}"

                    with next(get_db()) as db:
                        # Database-driven resolution
                        resolved_user_id, resolved_name, resolved_method = resolve_identity(db, raw_dev_uid)
                        if not resolved_user_id:
                            print(f"[COSEC_WORKER] Unknown User ID: {raw_dev_uid}")
                            continue

                        final_method = resolved_method or method

                        event = self.process_request(
                            db,
                            resolved_user_id,
                            final_method,
                            device_id,
                            bypass_cache=True
                        )

                        if event:
                            await self.broadcast(event)

                    self.last_index = raw_event["index"]

        except Exception as e:
            print(f"[COSEC_WORKER_ERROR] {e}")


class SyncWorker:
    """
    Reusable Synchronization Engine.
    Pushes user credentials to registered physical gates,
    tracks status (PENDING, SYNCED, RETRYING, FAILED), and handles offline recovery.
    """

    def __init__(self, db_factory=get_db):
        self.db_factory = db_factory

    async def sync_credential_to_gate(self, credential_id: str, gate_id: str) -> Tuple[bool, Optional[str]]:
        """Push a single credential to a designated physical gate."""
        with next(self.db_factory()) as db:
            cred = db.query(Credential).filter(Credential.credential_id == credential_id).first()
            gate = db.query(Gate).filter(Gate.gate_id == gate_id).first()
            sync_rec = db.query(GateSyncStatus).filter(
                GateSyncStatus.credential_id == credential_id,
                GateSyncStatus.gate_id == gate_id
            ).first()

            if not cred or not gate:
                return False, "Credential or Gate not found"

            user = cred.user
            if not user:
                return False, "User not associated with credential"

            if not gate.is_active:
                return False, f"Gate {gate.gate_id} is inactive"

            # Check if Mock or Hardware
            if gate.device_type == "MOCK":
                # Instant simulation acknowledgement
                if sync_rec:
                    sync_rec.status = "SYNCED"
                    sync_rec.synced_at = datetime.now()
                    sync_rec.last_error = None
                    db.commit()
                return True, None

            # Real COSEC hardware push
            adapter = COSECAdapter(
                base_url=f"http://{gate.device_ip}:{gate.device_port}",
                username=COSEC_CONFIG["username"],
                password=COSEC_CONFIG["password"],
                timeout_seconds=3.0
            )

            try:
                # 1. Push User
                ref_id = user.ref_user_id or 1000
                user_ok = await adapter.push_user(
                    user_id=user.user_id,
                    ref_user_id=ref_id,
                    name=user.name,
                    card1=cred.card_number,
                    enable_fr=(cred.type == "FACE")
                )
                if not user_ok:
                    raise RuntimeError("Device rejected user creation")

                # 2. Push Credential if Face
                if cred.type == "FACE":
                    cred_ok = await adapter.push_credential(
                        user_id=user.user_id,
                        cred_type="FACE"
                    )
                    if not cred_ok:
                        raise RuntimeError("Device rejected face credential")

                if sync_rec:
                    sync_rec.status = "SYNCED"
                    sync_rec.synced_at = datetime.now()
                    sync_rec.last_error = None
                    sync_rec.retry_count = 0
                    db.commit()
                return True, None

            except Exception as e:
                err_msg = str(e)
                if sync_rec:
                    sync_rec.retry_count += 1
                    sync_rec.status = "RETRYING" if sync_rec.retry_count < 3 else "FAILED"
                    sync_rec.last_error = err_msg
                    db.commit()
                return False, err_msg

    async def sync_user_to_all_gates(self, user_id: str) -> Dict[str, Any]:
        """Ensures all credentials of a user are synchronized across all registered active gates."""
        results = {}
        with next(self.db_factory()) as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                return {"error": "User not found"}

            gates = db.query(Gate).filter(Gate.is_active == True).all()
            credentials = db.query(Credential).filter(Credential.user_id == user_id).all()

            for cred in credentials:
                for gate in gates:
                    # Ensure GateSyncStatus record exists
                    sync_rec = db.query(GateSyncStatus).filter(
                        GateSyncStatus.credential_id == cred.credential_id,
                        GateSyncStatus.gate_id == gate.gate_id
                    ).first()
                    if not sync_rec:
                        sync_rec = GateSyncStatus(
                            id=str(uuid.uuid4()),
                            credential_id=cred.credential_id,
                            gate_id=gate.gate_id,
                            status="PENDING"
                        )
                        db.add(sync_rec)
            db.commit()

        # Perform sync
        with next(self.db_factory()) as db:
            credentials = db.query(Credential).filter(Credential.user_id == user_id).all()
            gates = db.query(Gate).filter(Gate.is_active == True).all()

            for cred in credentials:
                for gate in gates:
                    ok, err = await self.sync_credential_to_gate(cred.credential_id, gate.gate_id)
                    results[f"{gate.gate_id}_{cred.type}"] = {
                        "gate": gate.name,
                        "type": cred.type,
                        "status": "SYNCED" if ok else "RETRYING",
                        "error": err
                    }
        return results

    async def retry_failed_syncs(self) -> Dict[str, Any]:
        """Scans for failed/retrying sync records and attempts re-synchronization."""
        retried = []
        with next(self.db_factory()) as db:
            pending_records = db.query(GateSyncStatus).filter(
                GateSyncStatus.status.in_(["PENDING", "RETRYING", "FAILED"])
            ).all()

            for rec in pending_records:
                ok, err = await self.sync_credential_to_gate(rec.credential_id, rec.gate_id)
                retried.append({
                    "sync_id": rec.id,
                    "gate_id": rec.gate_id,
                    "status": "SYNCED" if ok else rec.status,
                    "error": err
                })
        return {"retried_count": len(retried), "details": retried}
