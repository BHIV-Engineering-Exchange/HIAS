# 01_CURRENT_RUNTIME_MAP.md — HIAS End-to-End Runtime Architecture

## 1. Architectural Runtime Overview

HIAS (Hostel Intelligence & Access System) operates as a centralized, deterministic access control controller.
The runtime path guarantees strict single-source-of-truth semantics from physical reader to the administrative dashboard:

```
+-----------------------------------------------------------------------------------+
| PHYSICAL / SIMULATED HARDWARE LAYER                                               |
|  - Matrix COSEC ARGO FACE (Girls Hostel In: 192.168.1.100)                        |
|  - Matrix COSEC ARGO FACE (Girls Hostel Out: 192.168.1.101)                       |
|  - Matrix COSEC PATH CONTROLLER (Dining Hall: 192.168.1.102)                      |
|  - Raspberry Pi GPIO 17 Relay Unit (Physical Solenoid Turnstile Trigger)          |
+-----------------------------------------------------------------------------------+
                                    |
                    HTTP CGI / TCP Poll / Webhook
                                    v
+-----------------------------------------------------------------------------------+
| FASTAPI BACKEND CORE (:8000)                                                      |
|                                                                                   |
|  [COSECAdapter] (backend/app/adapters/cosec.py)                                   |
|   - Formulates Matrix HTTP CGI requests (GET/POST /device.cgi/...)                |
|   - Decodes official XML event payloads & Detail-3 bitmasks                       |
|                                                                                   |
|  [CosecWorker & SyncWorker] (backend/app/background.py)                           |
|   - Database-Driven Identity Resolution (resolve_identity)                        |
|   - Multi-Gate Credential Provisioning Push Engine                                |
|   - Offline State & Retry Tracking (GateSyncStatus)                               |
|                                                                                   |
|  [Deterministic Decision Engine] (backend/app/engine.py)                          |
|   - Rule 0: Emergency Mode Bypass                                                 |
|   - Rule 1: Identity & Credential Existence (User / Credential lookup)            |
|   - Rule 2: Access Time Window (HH:MM arithmetic with midnight crossover)         |
|   - Absolute determinism: 0 probabilistic or AI dependencies in gate loop        |
|                                                                                   |
|  [Hardware Abstraction Layer] (backend/app/hardware.py)                           |
|   - Pulses GPIO 17 (1.5s active high) or triggers remote /device.cgi/command      |
|                                                                                   |
|  [Central Database Layer] (backend/app/models.py, hias.db / PostgreSQL)           |
|   - User (Canonical Resident)                                                     |
|   - Credential (RFID 64-bit CSN, Face template, PIN)                              |
|   - Gate (Physical terminal registry)                                             |
|   - GateSyncStatus (State machine: PENDING, SYNCED, RETRYING, FAILED)             |
|   - Event (Traceable audit trail)                                                 |
|   - Setting (Dynamic system settings)                                             |
|                                                                                   |
|  [Real-Time SSE Broadcasting] (/events/stream)                                    |
|   - Async queues with 15s keep-alive heartbeat comments                           |
+-----------------------------------------------------------------------------------+
                                    |
                           Server-Sent Events (SSE)
                                    v
+-----------------------------------------------------------------------------------+
| REACT FRONTEND VITE SPA (:5173)                                                   |
|  - EventContext (Auto-reconnecting EventSource, connection watchdog)              |
|  - LiveMonitor & LiveFeed (Real-time decision ticker, sub-100ms UI update)        |
|  - Users Screen (One-click enrollment modal, multi-gate sync indicator)           |
|  - SystemStatus (Registered gates, latencies, database metrics)                  |
|  - ReviewQueue & ManualOverride (Human-in-the-loop fallback)                      |
+-----------------------------------------------------------------------------------+
```

---

## 2. Detailed Runtime Step-by-Step Flow

### A. Device Detection to Decision
1. **User Punch:** Resident presents RFID card `4455667788` or face at the physical Matrix COSEC terminal (e.g., Gate `GATE_GIRLS_IN`).
2. **Device Event Queue:** The device generates a record with `seq-No`, `date`, `time`, and `detail-3` bitmask (`258` for Card 1).
3. **Adapter Ingestion:** 
   - `CosecWorker` polls `/device.cgi/events?action=getevent`.
   - `COSECAdapter._parse_events` parses XML and decodes `detail-3` to `Method.RFID` and `Direction.IN`.
4. **Database Identity Resolution (`resolve_identity`):**
   - Queries `credentials` table for `card_number == '4455667788'`.
   - Extracts canonical `User` (`S2501`, "Pritesh Patra").
   - Eliminates hardcoded `USER_MAPPING` dictionary.
5. **Deterministic Evaluation (`evaluate`):**
   - Evaluates emergency mode (False).
   - Verifies resident active status (True).
   - Validates time window (07:00 – 21:00) using integer minute arithmetic.
   - Outputs: `Decision.ALLOW`, `Reason.VALID`.
6. **Relay Actuation:** `open_gate` triggers GPIO 17 high for 1.5 seconds or sends `/device.cgi/command?action=opendoor` to the gate.
7. **Database Persistence:** An immutable `Event` record is saved with unique `trace_id`.
8. **SSE Broadcast:** Event pushed to `SSE_CLIENTS` queues.
9. **UI Display:** React `LiveFeed` renders green "ALLOWED" row with sub-second latency.

---

## 3. Component Inventory & Audit Cleanup

| Component | Previous Audit State | Remediated Converged State | File Location |
|-----------|----------------------|----------------------------|---------------|
| **CORS Middleware** | `allow_origins=["*"]`, `allow_credentials=False` caused browser blocking on LAN. | Configured `allow_origin_regex=r"https?://.*"`, `allow_credentials=True`, `expose_headers=["*"]`. | [`backend/app/main.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/main.py) |
| **SSE Stream** | Dropped connections on proxy idle timeout; frontend froze without reconnect. | Added 15s keep-alive heartbeat comments (`: ping\n\n`) and client-side reconnect backoff. | [`backend/app/main.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/main.py), [`frontend/src/context/EventContext.jsx`](file:///c:/Users/PRITESH/Desktop/hias_combined/frontend/src/context/EventContext.jsx) |
| **User Identity** | Hardcoded `USER_MAPPING = {"12": "S001", "15": "S002"}` in background worker. | Database-driven `resolve_identity()` querying `Credential` and `User` tables for 2,500+ records. | [`backend/app/background.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/background.py) |
| **Credential Storage** | No credential table existed; credentials implied by user table or code. | Relational `Credential` table supporting `RFID` (64-bit CSN), `FACE`, and `PIN` with unique constraints. | [`backend/app/models.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/models.py) |
| **Gate Registry** | Static list in `/system/devices` endpoint; no physical gate tracking. | Relational `Gate` table storing physical terminal IP, port, direction, and device type. | [`backend/app/models.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/models.py) |
| **Sync Engine** | No multi-gate push mechanism existed. | Reusable `SyncWorker` pushing to COSEC CGI endpoints, tracking `GateSyncStatus` with retries. | [`backend/app/background.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/background.py) |
| **COSEC Protocol** | Hardcoded mock URLs (`/device.cgi/commands?cmd=open-door`). | Implemented official Matrix COSEC HTTP CGI specifications (`users`, `credential`, `command`, `events`). | [`backend/app/adapters/cosec.py`](file:///c:/Users/PRITESH/Desktop/hias_combined/backend/app/adapters/cosec.py) |
| **Frontend Config** | Hardcoded `http://localhost:8000` failed when accessed from LAN devices. | Dynamic host discovery via `window.location.hostname` ensures proper LAN communication. | [`frontend/src/api/config.js`](file:///c:/Users/PRITESH/Desktop/hias_combined/frontend/src/api/config.js) |
