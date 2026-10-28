# 06_SYNC_ENGINE.md — Multi-Gate Synchronization Engine

**Checkpoint:** Stage 5 — Sync to Gates: Device Integration  
**Lead Owner:** Pritesh Patra (RFID / COSEC) • Suraj (System Integration)  
**Status:** **OPERATIONAL & PROVEN**

---

## 1. Engine Objectives & Architecture

Hostel gates are physically distributed across multiple buildings (Block A, Block B, Dining Hall, Perimeter Gates). The `SyncWorker` engine ensures that once a user is enrolled in the central HIAS database, their credentials are automatically provisioned to all physical gates without human intervention.

### Core Architecture Components
1. **State Machine:** Explicit state transitions for every credential on every physical gate.
2. **COSEC CGI Dispatcher:** Formulates standard HTTP CGI provisioning commands.
3. **Resilience & Fault Isolation:** If Gate 2 is temporarily offline due to network maintenance, Gate 1 and Gate 3 continue functioning normally; Gate 2 transitions to `RETRYING` without blocking or corrupting state.
4. **Retry Loop:** Automatic retry mechanism on reconnect via `POST /sync/retry`.

```
                    Central Database
                     (GateSyncStatus)
                            |
                     [ SyncWorker ]
                     /      |      \
                    /       |       \
                   v        v        v
              Gate 1     Gate 2    Gate 3
           (Girls In)  (Girls Out) (Dining)
               |            |         |
           [SYNCED]    [RETRYING]  [SYNCED]
                        (Offline)
                            |
                   (Network Restored)
                            |
                   POST /sync/retry
                            v
                        [SYNCED]
```

---

## 2. Sync State Lifecycle

| Status | Definition | Trigger / Condition | Next State |
|--------|------------|---------------------|------------|
| **`PENDING`** | Credential created in DB; sync task queued. | Created by `POST /users/enroll` or credential addition. | `SYNCED` on success; `RETRYING` on network failure. |
| **`SYNCED`** | Verified acknowledged by physical device (`Response-Code=0`). | Device returns HTTP 200 with success code. | Terminal state (stable). |
| **`RETRYING`** | Device unreachable or timed out; `retry_count < 3`. | Connection timeout, socket error, or HTTP 5xx. | `SYNCED` on retry success; `FAILED` after 3 attempts. |
| **`FAILED`** | Exceeded maximum retry threshold (3 attempts). | Persistent offline state or hardware incompatibility. | Requires operator attention or manual `/sync/retry`. |
| **`REVOKED`** | Credential invalidated or student checked out. | User deactivated or card deleted. | Sent `action=delete` to device. |

---

## 3. Code Implementation (`backend/app/background.py`)

```python
class SyncWorker:
    def __init__(self, db_factory=get_db):
        self.db_factory = db_factory

    async def sync_credential_to_gate(self, credential_id: str, gate_id: str) -> Tuple[bool, Optional[str]]:
        with next(self.db_factory()) as db:
            cred = db.query(Credential).filter(Credential.credential_id == credential_id).first()
            gate = db.query(Gate).filter(Gate.gate_id == gate_id).first()
            sync_rec = db.query(GateSyncStatus).filter(
                GateSyncStatus.credential_id == credential_id,
                GateSyncStatus.gate_id == gate_id
            ).first()

            if not cred or not gate or not cred.user:
                return False, "Entity not found"

            # Simulation bypass
            if gate.device_type == "MOCK":
                if sync_rec:
                    sync_rec.status = "SYNCED"
                    sync_rec.synced_at = datetime.now()
                    sync_rec.last_error = None
                    db.commit()
                return True, None

            # Real COSEC Hardware Push
            adapter = COSECAdapter(
                base_url=f"http://{gate.device_ip}:{gate.device_port}",
                username=COSEC_CONFIG["username"],
                password=COSEC_CONFIG["password"],
                timeout_seconds=3.0
            )

            try:
                # Step 1: Push User Information
                ref_id = cred.user.ref_user_id or 1000
                user_ok = await adapter.push_user(
                    user_id=cred.user.user_id,
                    ref_user_id=ref_id,
                    name=cred.user.name,
                    card1=cred.card_number,
                    enable_fr=(cred.type == "FACE")
                )
                if not user_ok:
                    raise RuntimeError("Device rejected user creation")

                # Step 2: Push Face Credential if applicable
                if cred.type == "FACE":
                    cred_ok = await adapter.push_credential(
                        user_id=cred.user.user_id,
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
```

---

## 4. Verification Evidence & Offline Handling Test

In test `TestMultiGateSync.test_sync_worker_with_offline_retry`:
1. Created an offline gate configured with unroutable IP `192.168.99.99`.
2. Enrolled test student `SYNC_TEST_USER` with RFID card `8888999900`.
3. Executed `sync_credential_to_gate()`.
4. Verified that:
   - Operation returned `ok = False` cleanly without unhandled exception.
   - Database record `GateSyncStatus` transitioned to `RETRYING`.
   - `retry_count` incremented to `1`.
   - Error string recorded in `last_error`.
   - Central `User` record was **not** duplicated or corrupted.
5. Simulated network recovery: re-executing `sync_credential_to_gate()` against an active gate transitioned status to `SYNCED`.
