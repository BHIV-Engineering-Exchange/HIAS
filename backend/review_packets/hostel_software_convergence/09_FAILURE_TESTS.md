# 09_FAILURE_TESTS.md — Negative & Failure Mode Verification

**Checkpoint:** Stage 6 — Test Everything: Prove It Works  
**Owners:** Pritesh Patra (RFID & Access Tests) • Shivam (Error Boundaries)  
**Status:** **100% VERIFIED**

---

## 1. Failure Testing Philosophy

In access control, an insecure failure can cause physical security breaches (tailgating, unauthorized entry) or lockouts during emergencies. All failure modes must be explicitly anticipated, bounded, and audited.

---

## 2. Failure Matrix & Test Proofs

| Failure Scenario | Input Condition | Expected System Behavior | HTTP Status | Measured Result |
|------------------|-----------------|--------------------------|:-----------:|:---------------:|
| **Unknown Credential** | Unregistered card `UNKNOWN_CARD_9999` at turnstile. | Decision `DENY`, Reason `UNKNOWN`, event logged to DB, alert raised on dashboard. | `200 OK` (Event payload) | **VERIFIED** |
| **Duplicate User ID** | Re-enrolling existing user `S2501`. | Rejection with descriptive message; no database corruption. | `400 Bad Request` | **VERIFIED** |
| **Duplicate RFID Card** | Assigning active card `4455667788` to a second user `S2502`. | Rejection with conflict error pointing to current card owner. | `409 Conflict` | **VERIFIED** |
| **Curfew / Time Block** | Swiping outside allowed window (e.g. 23:00 curfew). | Decision `DENY`, Reason `TIME_BLOCK`, relay remains locked. | `200 OK` (Event payload) | **VERIFIED** |
| **Rapid Double Scan** | Same card swiped twice within 2.0 seconds. | Second scan suppressed by monotonic timestamp cache to prevent double relay firing. | `429 Too Many Requests` | **VERIFIED** |
| **Device Offline** | Syncing to gate at unreachable IP (`192.168.99.99`). | `GateSyncStatus` marks `RETRYING`, logs error, increments retry count; central user remains valid. | Handled gracefully | **VERIFIED** |
| **Malformed JSON Body** | Missing required fields or non-JSON content. | Pydantic validation error caught at middleware boundary. | `422 Unprocessable Entity` | **VERIFIED** |

---

## 3. Detailed Failure Execution Samples

### 3.1 Unknown RFID Card Denied
```http
POST /access/event HTTP/1.1
Content-Type: application/json

{
  "user_id": "9999888877",
  "method": "RFID",
  "device_id": "GATE_GIRLS_IN"
}

HTTP/1.1 200 OK
{
  "trace_id": "5e1a0671-8931-4ce8-89c5-34200ea88812",
  "user_id": "9999888877",
  "name": "Unknown User",
  "direction": "IN",
  "method": "RFID",
  "decision": "DENY",
  "reason": "UNKNOWN",
  "device_id": "GATE_GIRLS_IN",
  "timestamp": "2026-10-28T18:22:15.110294"
}
```
*Result:* Relay is **not** energized (`[RELAY_TRIGGERED]` omitted). Alert added to `GET /alerts`.

### 3.2 Duplicate RFID Card Collision
```http
POST /users/enroll HTTP/1.1
Content-Type: application/json

{
  "user_id": "S2502",
  "name": "Sneha Gupta",
  "role": "Resident",
  "rfid_card": "4455667788"
}

HTTP/1.1 409 Conflict
{
  "detail": "RFID card 4455667788 is already assigned to user S2501"
}
```

### 3.3 Rapid Duplicate Scan Suppression
```http
POST /access/event HTTP/1.1
{"user_id": "S001", "method": "RFID", "device_id": "GATE_GIRLS_IN"} -> 200 OK

POST /access/event HTTP/1.1 (0.2s later)
{"user_id": "S001", "method": "RFID", "device_id": "GATE_GIRLS_IN"}

HTTP/1.1 429 Too Many Requests
{
  "detail": "Duplicate scan ignored"
}
```

### 3.4 Unreachable Terminal Device Handling
```python
ok, err = await worker.sync_credential_to_gate(cred_id, "GATE_OFFLINE_TEST")
assert ok is False
# Verifying database record:
rec = db.query(GateSyncStatus).filter(GateSyncStatus.id == sync_id).first()
assert rec.status == "RETRYING"
assert rec.retry_count == 1
assert "ConnectError" in rec.last_error or "failed" in rec.last_error.lower()
```
*Result:* Database state is preserved; no duplicate records created.
