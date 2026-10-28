# 13_HANDOVER.md — Engineering Handover & Architecture Index

**Project:** HIAS Hostel Software Convergence Mission  
**Primary Submitter:** Pritesh Patra (RFID / COSEC / Access Flow)  
**Co-Owners:** Shivam (Backend/Runtime) • Suraj (Site Integration)  
**Status:** **FINAL HANDOVER ACCEPTED**

---

## 1. Handover Statement

The build is complete. Any incoming engineer can clone this repository, run the test suites, start the application, reproduce the one-click enrollment flow, verify device synchronization across gates, inspect central audit event logs, and understand all architectural decisions without requiring undocumented tribal knowledge.

**Final Mission Target Achieved:**  
*One Team. One HIAS. One Identity. One Enrollment. Multiple Gates. Central Truth. Real Evidence.*

---

## 2. Codebase Directory & File Navigation

```text
hias_combined/
├── backend/
│   ├── app/
│   │   ├── adapters/
│   │   │   └── cosec.py          # Matrix COSEC HTTP CGI Client (XML parsing, bitmasks)
│   │   ├── background.py         # CosecWorker (polling) & SyncWorker (provisioning engine)
│   │   ├── database.py           # SQLAlchemy Engine, SessionLocal, Base
│   │   ├── engine.py             # Deterministic Decision Engine (Rule 0, 1, 2) & seed_db
│   │   ├── hardware.py           # RPi.GPIO 17 relay controller & hardware abstraction
│   │   ├── logger.py             # Non-blocking async event logging
│   │   ├── main.py               # FastAPI Controller, CORS, SSE Heartbeat, REST APIs
│   │   ├── models.py             # Relational Schema (User, Credential, Gate, Event...)
│   │   └── schemas.py            # Strict Pydantic Models for inbound/outbound contracts
│   └── tests/
│       ├── integration/
│       │   ├── test_api.py       # Core controller integration tests
│       │   └── test_convergence_mission.py # 11 Convergence Mission outcome tests
│       ├── unit/
│       │   ├── test_cosec_adapter.py # CGI URL & command unit tests
│       │   ├── test_engine.py    # Determinism & time window unit tests
│       │   └── test_schemas.py   # Schema validation tests
│       ├── mock_cosec.py         # Matrix COSEC ARGO/PATH terminal emulator
│       └── run_system_test.py    # Autonomous hardware system integration runner
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── config.js         # Dynamic host/port resolution for LAN & Cloud
│   │   ├── context/
│   │   │   └── EventContext.jsx  # SSE EventSource watchdog with auto-reconnect
│   │   ├── screens/
│   │   │   ├── Dashboard.jsx     # High-level metrics & quick actions
│   │   │   ├── LiveMonitor.jsx   # Real-time event ticker (< 100ms UI latency)
│   │   │   ├── Users.jsx         # One-Click Central Enrollment modal & registry
│   │   │   ├── SystemStatus.jsx  # Registered gates, latencies, & health metrics
│   │   │   ├── Reports.jsx       # Access logs & CSV exports
│   │   │   └── Settings.jsx      # Curfew times & emergency bypass toggle
│   └── package.json              # React 19, Vite 8, Lucide icons
├── review_packets/
│   └── hostel_software_convergence/ # Full 14-Document Audit & Evidence Packet
├── COSEC DEVICES API GUIDE.pdf   # Official Matrix hardware specification reference
├── pytest.ini                    # Root pytest configuration
└── requirements.txt              # 13 pinned dependencies (zero unpinned '>=')
```

---

## 3. Five-Minute Verification Checklist for Incoming Engineers

1. **Verify All Unit & Integration Tests:**
   ```bash
   pytest
   ```
   *Expected:* `130 passed` in ~9 seconds (100% pass rate).

2. **Verify Backend Tests:**
   ```bash
   pytest backend/tests
   ```
   *Expected:* `88 passed` in ~7 seconds.

3. **Verify Asynchronous System Test:**
   ```bash
   python backend/tests/run_system_test.py
   ```
   *Expected:* `[SUCCESS] SYSTEM TEST PASSED! Hardware events polled, resolved, evaluated, and committed.`

4. **Verify Frontend Production Build:**
   ```bash
   npm --prefix frontend run build
   ```
   *Expected:* Vite build complete with 0 errors.

---

## 4. Known Hardware Realities & Boundaries

1. **Matrix COSEC ARGO Face Image Upload:**
   - Supported format: JPEG only.
   - Maximum size: 200 KB per photo.
   - Endpoint: `POST /device.cgi/credential?action=set&type=6&user-id=<uid>`.
2. **Raspberry Pi GPIO Pinout:**
   - Relay signal pin: **BCM GPIO 17** (Physical Pin 11).
   - Pulse duration: **1.5 seconds**. Active HIGH.
   - When executed on a non-Pi machine (Windows / macOS / x86 VM), the hardware abstraction layer automatically switches to `[SIMULATION]` mode without crashing.
3. **Curfew Window Midnight Crossing:**
   - When curfew crosses midnight (e.g., `22:00` to `06:00`), `is_within_time_window()` converts timestamps to integer minutes-since-midnight arithmetic: `now >= start or now <= end`.
4. **Duplicate Punch Suppression:**
   - Turnstiles reject subsequent card punches by the same resident at the same gate within **2.0 seconds** (`DUPLICATE_THRESHOLD`), returning HTTP 429.

