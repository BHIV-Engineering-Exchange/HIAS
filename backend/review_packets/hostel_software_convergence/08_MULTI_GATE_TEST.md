# 08_MULTI_GATE_TEST.md — Multi-Gate Verification Evidence

**Checkpoint:** Stage 6 — Test Everything: Prove It Works  
**Owners:** Pritesh Patra (RFID / Access Flow) • Suraj (System Integration)  
**Status:** **PROVEN & PASSING**

---

## 1. Test Objective & Setup

Prove that once a resident is enrolled, their credential works seamlessly across multiple physical gates without requiring separate manual registration on each device.

### Gate Topology
- **Gate 1:** `GATE_GIRLS_IN` — Main Hostel Entrance (Direction: IN, IP: 192.168.1.100)
- **Gate 2:** `GATE_GIRLS_OUT` — Main Hostel Exit (Direction: OUT, IP: 192.168.1.101)
- **Gate 3:** `GATE_DINING_01` — Central Dining Hall (Direction: IN, IP: 192.168.1.102)

---

## 2. Test Execution Log: Multi-Gate Access Traversal

### Step 1: Central Enrollment
```http
POST /users/enroll HTTP/1.1
Content-Type: application/json

{
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "role": "Resident",
  "department": "Girls Hostel Block A",
  "rfid_card": "4455667788",
  "auto_sync": true
}

HTTP/1.1 200 OK
{
  "status": "success",
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "ref_user_id": 1007,
  "sync_report": {
    "GATE_GIRLS_IN_RFID": {"status": "SYNCED"},
    "GATE_GIRLS_OUT_RFID": {"status": "SYNCED"},
    "GATE_DINING_01_RFID": {"status": "SYNCED"}
  }
}
```

### Step 2: Access at Gate 1 (Girls Main IN)
```http
POST /access/event HTTP/1.1
Content-Type: application/json

{
  "user_id": "4455667788",
  "method": "RFID",
  "device_id": "GATE_GIRLS_IN"
}

HTTP/1.1 200 OK
{
  "trace_id": "c1f7a049-74d2-43bb-81ef-939e6a981c20",
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "direction": "IN",
  "method": "RFID",
  "decision": "ALLOW",
  "reason": "VALID",
  "device_id": "GATE_GIRLS_IN",
  "timestamp": "2026-10-28T18:09:23.909613"
}
```
*Relay Output:* `[RELAY_TRIGGERED] trace_id=c1f7a049 user_id=S2501 device=GATE_GIRLS_IN` (GPIO 17 High for 1.5s).

### Step 3: Access at Gate 2 (Girls Main OUT)
```http
POST /access/event HTTP/1.1
Content-Type: application/json

{
  "user_id": "4455667788",
  "method": "RFID",
  "device_id": "GATE_GIRLS_OUT"
}

HTTP/1.1 200 OK
{
  "trace_id": "f8a023b9-11ea-42ce-a7bc-204128f731e0",
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "direction": "OUT",
  "method": "RFID",
  "decision": "ALLOW",
  "reason": "VALID",
  "device_id": "GATE_GIRLS_OUT",
  "timestamp": "2026-10-28T18:14:10.104200"
}
```
*Direction Inferred:* Automatically assigned `OUT` by inspecting the `Gate` registry definition for `GATE_GIRLS_OUT`.

### Step 4: Access at Gate 3 (Dining Hall)
```http
POST /access/event HTTP/1.1
Content-Type: application/json

{
  "user_id": "4455667788",
  "method": "RFID",
  "device_id": "GATE_DINING_01"
}

HTTP/1.1 200 OK
{
  "trace_id": "18ac2854-32bc-48d1-9f90-e59392ab00c4",
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "direction": "IN",
  "method": "RFID",
  "decision": "ALLOW",
  "reason": "VALID",
  "device_id": "GATE_DINING_01",
  "timestamp": "2026-10-28T18:20:05.512390"
}
```

---

## 3. Automated Test Proof

From `backend/tests/integration/test_convergence_mission.py`:
- `test_rfid_card_access_allow`: Verified card CSN `4455667788` maps to `S2501` at `GATE_GIRLS_IN`. **PASSED**
- `test_rfid_exit_direction_inference`: Verified exit direction on `GATE_GIRLS_OUT`. **PASSED**
- All 3 access events recorded immutably in SQLite database and verified in table output.
