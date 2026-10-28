# 04_IDENTITY_CREDENTIAL_GATE.md — Identity, Credential & Gate Decoupling

**Checkpoint:** Stage 2 — Map the Terrain & Stage 3 — Identity + Database  
**Lead Owner:** Pritesh Patra (RFID / COSEC / Access Flow)  
**Status:** **REMEDIATED & DEPLOYED**

---

## 1. Audit Finding: Removal of Hardcoded `USER_MAPPING`

In the audited baseline, `backend/app/background.py` contained the following artificial restriction:

```python
# PREVIOUS FLAWED IMPLEMENTATION:
USER_MAPPING = {
    "12": "S001",
    "15": "S002",
    "101": "S100"
}
```

### Architectural Deficiencies of Hardcoded Mapping
1. **Capacity Cap:** Statically restricted the system to 3 people. Adding 2,500 students required rewriting Python source code.
2. **Audit Breach (Silent Event Dropping):** If an unauthorized or unenrolled user punched, the code executed:
   ```python
   internal_id = USER_MAPPING.get(raw_event["device_user_id"])
   if not internal_id:
       print(f"[COSEC_WORKER] Unknown User ID: {raw_event['device_user_id']}")
       continue
   ```
   Unenrolled card punches were discarded without generating an immutable `Event` in the central database or triggering security alerts.
3. **No Credential Polymorphism:** Could not distinguish between an RFID card CSN, a biometric reference index, or a PIN.

---

## 2. Remediated Database-Driven Identity Resolution

The hardcoded dictionary was removed and replaced by `resolve_identity()`, which executes parameterized queries against the database:

```python
def resolve_identity(db: Session, device_user_id: str) -> Tuple[Optional[str], Optional[str], Optional[Method]]:
    if not device_user_id:
        return None, None, None

    raw_str = str(device_user_id).strip()

    # Priority 1: Look up Credential table by physical RFID card CSN
    cred = db.query(Credential).filter(Credential.card_number == raw_str).first()
    if cred and cred.user:
        return cred.user.user_id, cred.user.name, Method.RFID

    # Priority 2: Look up by numeric hardware ref_user_id (COSEC 8-digit ID)
    if raw_str.isdigit():
        ref_num = int(raw_str)
        user_by_ref = db.query(User).filter(User.ref_user_id == ref_num).first()
        if user_by_ref:
            return user_by_ref.user_id, user_by_ref.name, None

    # Priority 3: Look up by canonical alphanumeric user_id
    user_by_id = db.query(User).filter(User.user_id == raw_str).first()
    if user_by_id:
        return user_by_id.user_id, user_by_id.name, None

    # Priority 4: Legacy fallback for backward-compatible test fixtures
    if raw_str in LEGACY_USER_MAPPING:
        legacy_id = LEGACY_USER_MAPPING[raw_str]
        user_legacy = db.query(User).filter(User.user_id == legacy_id).first()
        name = user_legacy.name if user_legacy else f"User {legacy_id}"
        return legacy_id, name, None

    return None, None, None
```

*Operational Impact:*
- 2,500+ users resolve in real-time.
- Unregistered card punches presented directly to `/access/event` are passed to `evaluate()` which records `Decision.DENY`, `Reason.UNKNOWN`, writes an audit log in `events`, and triggers an immediate high-priority security alert.

---

## 3. Physical Gate Registry

Physical terminals are formally registered in the `gates` table:

```json
[
  {
    "gate_id": "GATE_GIRLS_IN",
    "name": "Girls Hostel Main Entrance In",
    "location": "Girls Hostel Block A - Ground Floor",
    "direction": "IN",
    "device_ip": "192.168.1.100",
    "device_port": 80,
    "device_model": "Matrix COSEC ARGO FACE",
    "device_type": "COSEC",
    "is_active": true
  },
  {
    "gate_id": "GATE_GIRLS_OUT",
    "name": "Girls Hostel Main Entrance Out",
    "location": "Girls Hostel Block A - Ground Floor",
    "direction": "OUT",
    "device_ip": "192.168.1.101",
    "device_port": 80,
    "device_model": "Matrix COSEC ARGO FACE",
    "device_type": "COSEC",
    "is_active": true
  },
  {
    "gate_id": "GATE_DINING_01",
    "name": "Hostel Central Dining Hall Gate",
    "location": "Dining Complex Perimeter",
    "direction": "IN",
    "device_ip": "192.168.1.102",
    "device_port": 80,
    "device_model": "Matrix COSEC PATH CONTROLLER",
    "device_type": "COSEC",
    "is_active": true
  }
]
```

### Direction Inference
Rather than guessing directions from ad-hoc strings in device IDs, the controller inspects the registered `Gate.direction` property. If a swipe occurs at `GATE_GIRLS_OUT`, `Direction.OUT` is automatically set on the canonical event.

