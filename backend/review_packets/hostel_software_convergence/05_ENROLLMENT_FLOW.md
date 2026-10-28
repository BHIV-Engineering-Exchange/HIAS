# 05_ENROLLMENT_FLOW.md — One-Click Central Enrollment Flow

**Checkpoint:** Stage 4 — Enable Enrollment: One Person, One Flow  
**Lead Owner:** Pritesh Patra (RFID / COSEC / Access Flow)  
**Status:** **IMPLEMENTED & VERIFIED**

---

## 1. Enrollment Architecture Overview

Prior to this convergence, adding a new resident required separately typing the student's name into each physical Matrix door controller, manually assigning cards, and separately updating backend databases. This led to desynchronization, duplicate card collisions, and gate access failures.

HIAS implements **One-Click Central Enrollment (`POST /users/enroll`)**:
An administrator enters the student's details once. The system provisions the central identity, generates hardware credentials, and automatically fans out synchronization to all active physical gates.

```
       Admin Form (Frontend :5173 / API Client)
                         |
           POST /users/enroll (JSON payload)
                         v
       +------------------------------------+
       | Fast API Controller Validation     |
       |  1. Validate User ID format        |
       |  2. Duplicate User ID Check (400)  |
       |  3. Duplicate Card CSN Check (409) |
       +------------------------------------+
                         |
                         v
       +------------------------------------+
       | Central Database Transaction       |
       |  1. Allocate ref_user_id (e.g 1007)|
       |  2. Insert 'users' record          |
       |  3. Insert 'credentials' (RFID)    |
       |  4. Insert 'gate_sync_status' rows |
       +------------------------------------+
                         |
                         v
       +------------------------------------+
       | SyncWorker Provisioning Push       |
       |  -> Gate 1 (Girls Main IN)         |
       |  -> Gate 2 (Girls Main OUT)        |
       |  -> Gate 3 (Central Dining)        |
       +------------------------------------+
                         |
                         v
          200 OK + Real-Time Sync Report
```

---

## 2. API Contract: `POST /users/enroll`

### Request Payload (`UserEnrollInput`)
```json
{
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "role": "Resident",
  "department": "Girls Hostel Block A - Room 101",
  "rfid_card": "4455667788",
  "face_data": "COSEC_ARGO_FACE_TEMPLATE_PRITESH",
  "auto_sync": true
}
```

### Response Payload
```json
{
  "status": "success",
  "user_id": "S2501",
  "name": "Pritesh Patra",
  "ref_user_id": 1007,
  "role": "Resident",
  "credentials": [
    {
      "credential_id": "9d81fc20-df70-42f0-91c2-c07a3c306e01",
      "type": "RFID",
      "card_number": "4455667788"
    },
    {
      "credential_id": "3b2e5910-449e-4a61-b541-03e33b664722",
      "type": "FACE",
      "card_number": null
    }
  ],
  "sync_report": {
    "GATE_GIRLS_IN_RFID": {
      "gate": "Girls Hostel Main Entrance In",
      "type": "RFID",
      "status": "SYNCED",
      "error": null
    },
    "GATE_GIRLS_OUT_RFID": {
      "gate": "Girls Hostel Main Entrance Out",
      "type": "RFID",
      "status": "SYNCED",
      "error": null
    },
    "GATE_DINING_01_RFID": {
      "gate": "Hostel Central Dining Hall Gate",
      "type": "RFID",
      "status": "SYNCED",
      "error": null
    }
  }
}
```

---

## 3. Duplicate Prevention & Security Guarantees

### A. Duplicate User ID Prevention
If an administrator attempts to enroll `S2501` twice:
- **Status:** `HTTP 400 Bad Request`
- **Body:** `{"detail": "User ID already exists"}`
- Verified in automated test: `test_duplicate_user_id_rejected`.

### B. Duplicate RFID Card Protection
If an administrator attempts to assign an already-registered card number (`4455667788`) to another student `S2502`:
- **Status:** `HTTP 409 Conflict`
- **Body:** `{"detail": "RFID card 4455667788 is already assigned to user S2501"}`
- Prevents cross-resident impersonation and dual-access anomalies.
- Verified in automated test: `test_duplicate_rfid_card_rejected`.

---

## 4. UI Implementation (`frontend/src/screens/Users.jsx`)

The React frontend includes a responsive modal allowing single-screen enrollment:
- Real-time form input fields for User ID, Name, Role, Room, and RFID Card.
- Instant validation alerts for duplicate cards or IDs.
- Multi-Gate sync status indicators showing `3/3 Gates Synced` with green health badges.
