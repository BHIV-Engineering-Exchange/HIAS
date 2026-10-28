# 11_DEPLOYMENT_RUNBOOK.md — Onsite & Cloud Deployment Runbook

**Audience:** Site Engineers • System Administrators • Fresh Onboarding Developers  
**Maintainers:** Shivam (Backend/Deployment) • Pritesh (Hardware Verification) • Suraj (Site Integration)  
**Status:** **TESTED & REPRODUCIBLE**

---

## 1. System Prerequisites

- **Runtime Environments:**
  - Python 3.11+
  - Node.js 18+ (Node 24 recommended)
  - Git
- **Network Requirements:**
  - Static IP assigned to HIAS Controller host (e.g. `192.168.1.50`).
  - Physical Matrix COSEC devices accessible via TCP port 80 on same subnet (e.g. `192.168.1.100` – `192.168.1.102`).
  - Open inbound ports: `8000` (FastAPI Core) and `5173` (React Frontend).

---

## 2. Fast-Track Reproduction (Step-by-Step)

### Step 1: Clone & Environment Setup
```bash
git clone https://github.com/Soham20030/HIAS.git
cd HIAS

# Setup Python Virtual Environment
python -m venv venv
# Linux / macOS:
source venv/bin/activate
# Windows:
.\venv\Scripts\Activate.ps1

# Install strict pinned dependencies
pip install -r requirements.txt
```

### Step 2: Build React Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

### Step 3: Run Full Automated Verification Suite
```bash
# Run 130 comprehensive unit & integration tests
pytest

# Run the complete asynchronous hardware system test
python backend/tests/run_system_test.py
```
*Expected Output:* `[SUCCESS] SYSTEM TEST PASSED! Hardware events polled, resolved, evaluated, and committed.`

---

## 3. Production Deployment Commands

### Option A: Local / Raspberry Pi Onsite Execution
```bash
# Terminal 1: Start Mock or Connect to Real Matrix COSEC
python backend/tests/mock_cosec.py

# Terminal 2: Start HIAS Controller Core
cd backend
export DATABASE_URL="sqlite:///./hias.db"
export COSEC_BASE_URL="http://192.168.1.100"
export COSEC_WORKER_ENABLED="true"
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Start Frontend SPA
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

### Option B: Docker Compose Deployment
```bash
docker-compose up -d --build
```
Access points:
- **Hostel Dashboard:** `http://<HOST_IP>:5173`
- **Controller Core API:** `http://<HOST_IP>:8000`
- **Interactive Swagger Docs:** `http://<HOST_IP>:8000/docs`

---

## 4. Key Configuration Variables (`.env`)

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `PORT` | `8000` | Port for FastAPI HTTP/SSE server |
| `DATABASE_URL` | `sqlite:///./hias.db` | Central SQLite path or PostgreSQL connection string |
| `COSEC_BASE_URL` | `http://192.168.1.100` | IP/Base URL of primary Matrix COSEC terminal |
| `COSEC_USERNAME` | `admin` | Matrix COSEC HTTP basic auth username |
| `COSEC_PASSWORD` | `password123` | Matrix COSEC HTTP basic auth password |
| `COSEC_POLL_INTERVAL` | `2.0` | Event poll interval in seconds |
| `COSEC_WORKER_ENABLED`| `true` | Enables background COSEC polling loop |
| `VITE_API_URL` | Auto-detected | Frontend override (leave empty for dynamic LAN discovery) |

---

## 5. Onsite Troubleshooting Guide

### 1. "Frontend says Disconnected / CORS Error"
- Run `curl -I http://<BACKEND_IP>:8000/health`. Ensure HTTP 200 response.
- Verify preflight:
  ```bash
  curl -X OPTIONS http://<BACKEND_IP>:8000/access/event -H "Origin: http://<FRONTEND_IP>:5173" -I
  ```
- Check that `access-control-allow-origin` header is returned.

### 2. "Matrix Terminal Not Opening Turnstile"
- Check relay wiring: GPIO 17 on Raspberry Pi connected to relay module IN.
- Check simulated vs real mode: `GET http://<BACKEND_IP>:8000/health`. If running without Raspberry Pi GPIO hardware, HIAS logs `[SIMULATION] Relay ON for 1.5s` safely.
- If using remote COSEC door strike: verify terminal responds to `http://<DEVICE_IP>/device.cgi/check-enrollment`.

### 3. "Card Swiped but User Denied"
- Query `GET /users/search?q=<CARD_NUMBER>` to confirm card CSN is enrolled in the central database.
- Inspect `/settings` to verify access window (e.g. curfew hours).
