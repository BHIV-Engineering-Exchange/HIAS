# Storage Service — Immutable Event Storage

**The Single Source of Truth** — All backend services write into this service only.

---

## 🎯 Responsibility

✅ **Accept** structured events matching `storage.schema.json`  
✅ **Enforce** append-only writes (reject all mutations)  
✅ **Generate** and verify SHA-256 hash chain (tamper-proof)  
✅ **Persist** events to database with immutability guarantees  
✅ **Expose** read APIs for dashboard + integrations  
✅ **Emit** signals to observability service (Pravah)

---

## 📋 Constraints (NON-NEGOTIABLE)

❌ **NO UPDATE/DELETE operations** — Ever
❌ **NO direct database access** from other services  
❌ **NO mutations** to stored records  
❌ **NO bypassing** the `/store-event` API

✅ **ALL writes** via `/store-event` endpoint  
✅ **Every event** carries `trace_id` (immutable)  
✅ **Every record** has `hash` + `prev_hash` linkage  
✅ **Every event** validated against schema

---

## 🏗️ Architecture

```
Incoming Event
    ↓
[1] Schema Validation (storage.schema.json)
    ↓
[2] Mutation Check (trace_id already exists?)
    ↓
[3] Hash Chain Generation (SHA256)
    ↓
[4] Database Write (transactional)
    ↓
[5] Hash Chain Record Created
    ↓
[6] Stats Updated
    ↓
Response: {trace_id, event_id, hash, status}
```

---

## 🔗 Hash Chain (Core Innovation)

```
Event 1: hash = SHA256(GENESIS + event1_data)
Event 2: hash = SHA256(event1_hash + event2_data)
Event 3: hash = SHA256(event2_hash + event3_data)
```

**Why this matters:**
- ✅ Cannot modify past events (hash wouldn't match)
- ✅ Cannot reorder events (prev_hash wouldn't match)
- ✅ Cannot insert events (chain breaks)
- ✅ Complete tamper-evident audit trail
- ✅ Cryptographic verification without blockchain

---

## 📡 API Endpoints

### POST `/store-event`
**Store a new event (append-only)**

Input:
```json
{
  "trace_id": "HIAS-20260418-a1b2c3d4-000001",
  "timestamp": "2026-04-18T08:00:00Z",
  "student_id": "STU001",
  "event": "ENTRY",
  "confidence": 0.95,
  "status": "AUTO",
  "source_service": "confidence_service",
  "camera_id": "GATE-MAIN",
  "zone": "GATE_MAIN"
}
```

Output:
```json
{
  "trace_id": "HIAS-20260418-a1b2c3d4-000001",
  "event_id": "uuid",
  "hash": "abc123def456...",
  "prev_hash": "xyz789uvw012...",
  "status": "ACCEPTED"
}
```

### GET `/fetch-by-trace?trace_id=HIAS-...`
**Fetch all events in a trace**

Returns complete event history with hash chain linkage.

### GET `/fetch-by-student?student_id=STU001&date=2026-04-18&status=AUTO`
**Fetch attendance events for a student**

Filters: `date` (YYYY-MM-DD), `status` (AUTO/REVIEW/REJECT/CORRECTED)

### GET `/health`
Health check endpoint.

### GET `/stats`
Get storage statistics:
```json
{
  "total_events": 1234,
  "total_students": 456,
  "last_event_timestamp": "2026-04-18T12:30:00Z",
  "hash_chain_verified": true
}
```

---

## 🗂️ File Structure

```
storage-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app + endpoints
│   ├── writer.py         # Append-only write engine
│   ├── hash_chain.py     # SHA256 hash chain logic
│   ├── validator.py      # Schema validation
│   ├── models.py         # SQLAlchemy ORM models
│   ├── database.py       # DB initialization + sessions
│   └── config.py         # Configuration management
├── tests/
│   ├── test_append_only.py       # Append-only enforcement
│   ├── test_hash_chain.py        # Hash chain verification
│   ├── test_mutations.py         # Mutation rejection
│   └── test_integration.py       # Full pipeline tests
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Local Execution

### 1. Install Dependencies

```bash
cd storage-service
pip install -r requirements.txt
```

### 2. Configure Database

For local development (SQLite) — no setup needed.

For PostgreSQL:
```bash
# Create database
createdb hias_storage

# Update .env
export DATABASE_URL="postgresql://user:pass@localhost:5432/hias_storage"
```

### 3. Run Service

```bash
python -m app.main
# or
uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

Service runs on `http://localhost:8005`

### 4. Test API

```bash
# Store an event
curl -X POST http://localhost:8005/store-event \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": "HIAS-20260418-a1b2c3d4-000001",
    "timestamp": "2026-04-18T08:00:00Z",
    "student_id": "STU001",
    "event": "ENTRY",
    "confidence": 0.95,
    "status": "AUTO",
    "source_service": "confidence_service",
    "camera_id": "GATE-MAIN",
    "zone": "GATE_MAIN"
  }'

# Fetch by trace
curl http://localhost:8005/fetch-by-trace?trace_id=HIAS-20260418-a1b2c3d4-000001

# Get stats
curl http://localhost:8005/stats

# Health check
curl http://localhost:8005/health
```

---

## 📚 Core Implementation Details

### append_event() — Write Engine

1. Validate against storage.schema.json
2. Check for mutation (trace_id already exists?)
3. Generate SHA256 hash: `SHA256(prev_hash + event_data)`
4. Store event + hash chain record
5. Update statistics
6. Return response with hash proof

**Guarantees:**
- Atomic transaction (all or nothing)
- No partial writes
- Idempotent (same event twice = rejected on 2nd attempt)

### verify_chain_integrity()

Cryptographically verifies entire hash chain:
- Each event hash matches SHA256 formula
- prev_hash points to correct previous event
- No gaps in chain
- No tampering detected

### fetch_by_trace()

Returns complete event history for a trace_id in chronological order.

Useful for:
- Debugging specific events
- Audit trail replay
- Trace visibility (dashboard requirement)

---

## ✅ Non-Negotiable Rules

### Rule 1: Append-Only Enforcement
```python
# ❌ REJECTED
curl -X PUT /store-event/event-id -d '{"student_id": "NEW_ID"}'

# ✅ ACCEPTED
curl -X POST /store-event -d '{...new event...}'
```

### Rule 2: Trace ID Immutability
Every event carries its original trace_id through entire pipeline.

### Rule 3: Hash Chain Integrity
Every stored event part of cryptographic chain — cannot be isolated.

### Rule 4: Schema Validation
Every incoming event validated against storage.schema.json.

Failure → REJECTED (never partial/corrupt data stored)

### Rule 5: No Direct DB Access
```python
# ❌ NOT ALLOWED
from models import Event
session.query(Event).filter_by(trace_id='...').update({'student_id': 'NEW'})

# ✅ ONLY WAY
POST /store-event
```

---

## 🧪 Testing

Run tests:
```bash
pytest tests/
```

Key test files:
- **test_append_only.py** — Verify mutations are rejected
- **test_hash_chain.py** — Verify hash chain correctness
- **test_schema_validation.py** — Verify contract enforcement
- **test_integration.py** — End-to-end pipeline tests

---

## 🔍 Debugging

### Trace a specific event:
```bash
curl http://localhost:8005/fetch-by-trace?trace_id=HIAS-20260418-a1b2c3d4-000001
```

### Check hash chain integrity:
```python
from app.writer import StorageWriter
writer = StorageWriter()
result = writer.verify_chain_integrity()
print(result)  # {"valid": True, "total_events": 1000}
```

### View all events for a student:
```bash
curl "http://localhost:8005/fetch-by-student?student_id=STU001&date=2026-04-18"
```

---

## 🔧 Configuration

See `.env.example` for all settings.

Key configs:
- `DATABASE_URL` — PostgreSQL or SQLite
- `STRICT_SCHEMA_VALIDATION` — Reject invalid events
- `HASH_CHAIN_VERIFICATION_ENABLED` — Enable tamper detection
- `LOG_LEVEL` — INFO, DEBUG, WARNING, ERROR
- `EMIT_OBSERVABILITY_SIGNALS` — Send metrics to Pravah

---

## 📊 Owner & Team Integration

- **Owner:** Siddhesh (Storage Layer)
- **Inputs From:** Confidence Service, Human Loop Service
- **Outputs To:** Backend Integration Service, Dashboard Service
- **Signals To:** Observability Service (Pravah)

---

## ✨ Status

Phase 3 ✅ COMPLETE  
Phase 4 ✅ COMPLETE  
Phase 5 ✅ COMPLETE  

**Next:** Phase 6 — Storage Contract Enforcement + Phase 7 — Storage API Layer

---

**Last Updated:** 2026-04-18  
**System:** HIAS (Hostel Intelligence & Attendance System)  
**Build:** Fast Track — 10 Phases, 2-3 day execution

```bash
cd storage-service
pip install -r requirements.txt
python app/main.py
# Runs on http://localhost:8001
```

## Integration Point

Every other service must call:
```
POST http://storage-service:8001/store-event
```

No exceptions. No workarounds.

---

**This service IS the system integrity layer.**
