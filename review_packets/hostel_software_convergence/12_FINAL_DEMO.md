# 12_FINAL_DEMO.md — Live Demonstration Script & Protocol

**Checkpoint:** Stage 7 — Final Demo: Mission Complete  
**Demonstrator:** Pritesh Patra (RFID / Access Flow) • Team HIAS  
**Target Audience:** Engineering Evaluators, Hostel Wardens, Systems Auditors  
**Status:** **DEMO-READY & REPRODUCIBLE**

---

## 1. Demonstration Outline

This script provides an exact, reproducible sequence proving the five outcomes of the HIAS Convergence Mission:
1. **Outcome 1:** Database handles 2,500+ residents without hardcoded limits.
2. **Outcome 2:** Single central enrollment flow creates identity and credentials.
3. **Outcome 3:** One canonical database for users, credentials, gates, and events.
4. **Outcome 4:** Working Matrix COSEC RFID + Face integration.
5. **Outcome 5:** End-to-end multi-gate traversal with real-time SSE live feed visibility.

---

## 2. Step-by-Step Demonstration Script

### Part 1: Initial State & Health Inspection
1. **Launch Services:**
   - Backend on `http://localhost:8000`
   - Frontend on `http://localhost:5173`
   - Mock COSEC Terminal on `http://localhost:8080`
2. **Open Dashboard:** Navigate to `http://localhost:5173`.
3. **Verify Connectivity:**
   - Confirm the green status dot displays **"Connected"** (SSE stream active via `/events/stream`).
   - Open **System Status** tab: Observe registered gates:
     - `Girls Hostel Main Entrance In` (COSEC ARGO FACE) — Online
     - `Girls Hostel Main Entrance Out` (COSEC ARGO FACE) — Online
     - `Hostel Central Dining Hall Gate` (COSEC PATH) — Online

### Part 2: One-Click Central Enrollment
1. Navigate to **Users & Credentials** tab.
2. Click **"+ ONE-CLICK ENROLL"** button.
3. Input the resident details:
   - **User ID:** `S2501`
   - **Full Name:** `Pritesh Patra`
   - **Role:** `Resident`
   - **Department / Room:** `Girls Hostel Block A - Room 101`
   - **RFID Card CSN:** `4455667788`
   - **Options:** Check `Provision COSEC ARGO Face Recognition Template` and `Automatically Push & Sync to all Active Hostel Gates`.
4. Click **"ENROLL & SYNC"**.
5. **Observe Immediate Feedback:**
   - Green notification: `Enrolled successfully! Synchronized across active gates.`
   - Modal closes automatically.
   - User table updates immediately showing:
     - Name: `Pritesh Patra`
     - ID: `S2501 #1007`
     - Credentials: `RFID: 4455667788`, `FACE: ACTIVE`
     - Multi-Gate Sync: `3/3 Gates Synced`

### Part 3: Physical Access at Gate 1 (Girls Main IN)
1. Simulate or execute RFID card tap at Entrance Gate:
   ```bash
   curl -X POST http://localhost:8000/access/event -H "Content-Type: application/json" \
     -d '{"user_id": "4455667788", "method": "RFID", "device_id": "GATE_GIRLS_IN"}'
   ```
2. **Observe System Responses:**
   - **Terminal Log:** `[RELAY_TRIGGERED] trace_id=... user_id=S2501 device=GATE_GIRLS_IN` (Relay opens for 1.5s).
   - **Live Monitor Screen:** A new green row appears instantly at the top of the feed:
     - `Pritesh Patra (S2501)` | `RFID` | `GATE_GIRLS_IN` | `IN` | **`ALLOWED (VALID)`**
   - **Database:** Immutable row inserted into `events` table.

### Part 4: Traversal to Gate 2 (Girls Main OUT)
1. Resident leaves hostel; tap card at Exit Gate:
   ```bash
   curl -X POST http://localhost:8000/access/event -H "Content-Type: application/json" \
     -d '{"user_id": "4455667788", "method": "RFID", "device_id": "GATE_GIRLS_OUT"}'
   ```
2. **Observe System Responses:**
   - Controller automatically infers direction: **`OUT`** based on Gate definition.
   - Relay opens.
   - Live Feed shows: `Pritesh Patra (S2501)` | `RFID` | `GATE_GIRLS_OUT` | `OUT` | **`ALLOWED (VALID)`**.

### Part 5: Failure & Security Anomaly Demonstration
1. **Unauthorized / Stolen Card Test:**
   - Present an unregistered RFID card `UNKNOWN_9999`:
     ```bash
     curl -X POST http://localhost:8000/access/event -H "Content-Type: application/json" \
       -d '{"user_id": "UNKNOWN_9999", "method": "RFID", "device_id": "GATE_GIRLS_IN"}'
     ```
   - **Turnstile:** Remains firmly locked (`[RELAY_TRIGGERED]` does not fire).
   - **Live Feed:** Red row flashes: `Unknown User` | `DENIED (UNKNOWN)`.
   - **Alerts Screen:** High-severity alert appears: `Unauthorized Access Attempt: Unknown User (UNKNOWN_9999)`.
2. **Rapid Double Scan Test:**
   - Tap valid card twice in under 1 second.
   - Second tap receives HTTP 429 (`Duplicate scan ignored`), preventing turnstile desynchronization or motor burn-out.
3. **Duplicate Card Enrollment Test:**
   - Attempt to enroll another student using `4455667788`.
   - Form rejects submission with HTTP 409: `RFID card 4455667788 is already assigned to user S2501`.

---

## 3. Mission Acceptance Proof Checklist

- [x] Before/after proof of Girls Hostel CORS/SSE fix ([`02_CORS_SSE_FIX.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/02_CORS_SSE_FIX.md))
- [x] Central user created once via One-Click Enrollment ([`05_ENROLLMENT_FLOW.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/05_ENROLLMENT_FLOW.md))
- [x] Credential record created and associated in relational schema ([`03_DATABASE_SCHEMA.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/03_DATABASE_SCHEMA.md))
- [x] Gate/device registry populated from real deployment info ([`04_IDENTITY_CREDENTIAL_GATE.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/04_IDENTITY_CREDENTIAL_GATE.md))
- [x] Credential synchronized to multiple gates ([`06_SYNC_ENGINE.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/06_SYNC_ENGINE.md))
- [x] Successful access event from test device with relay trigger ([`08_MULTI_GATE_TEST.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/08_MULTI_GATE_TEST.md))
- [x] Central event visible in database and dashboard SSE feed
- [x] Unknown/invalid credential denied correctly ([`09_FAILURE_TESTS.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/09_FAILURE_TESTS.md))
- [x] Offline/retry behavior demonstrated without data loss ([`06_SYNC_ENGINE.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/06_SYNC_ENGINE.md))
- [x] 2,500+ capacity/load evidence ([`10_PERFORMANCE.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/10_PERFORMANCE.md))
- [x] Clean run instructions for any engineer to reproduce result ([`11_DEPLOYMENT_RUNBOOK.md`](file:///c:/Users/PRITESH/Desktop/hias_combined/review_packets/hostel_software_convergence/11_DEPLOYMENT_RUNBOOK.md))

