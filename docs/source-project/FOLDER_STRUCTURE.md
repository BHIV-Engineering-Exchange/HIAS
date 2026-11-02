# Folder Structure & Naming Conventions

## Repos are Sacred — DO NOT Deviate

Every service must live in this repo. No separate repos allowed.

---

## Unified Structure (Frozen)

```
hias-system/
├── README.md                           # System overview
├── FOLDER_STRUCTURE.md                 # This file
├── .env                                # Environment variables (gitignored)
├── .gitignore                          # Standard ignore rules
├── .git/                               # Git repo root
│
├── shared-contracts/
│   ├── __init__.py
│   ├── schemas/
│   │   ├── ingestion.schema.json       # Input from camera / simulator
│   │   ├── recognition.schema.json     # Face detection output
│   │   ├── intelligence.schema.json    # Entry/exit events
│   │   ├── confidence.schema.json      # Confidence routing decision
│   │   ├── human_loop.schema.json      # Manual correction input
│   │   ├── storage.schema.json         # What storage service accepts
│   │   ├── observability.schema.json   # Pravah signal format
│   │   └── error.schema.json           # Standard error contract
│   ├── validators.py                   # Pydantic models + validation logic
│   └── requirements.txt                # Shared dependencies (Pydantic, jsonschema)
│
├── storage-service/
│   ├── app/
│   │   ├── main.py                     # FastAPI app + uvicorn startup
│   │   ├── config.py                   # DB connection, constants
│   │   ├── models.py                   # SQLAlchemy ORM models
│   │   ├── schemas.py                  # Pydantic schemas (input/output)
│   │   ├── api.py                      # API routes
│   │   ├── writer.py                   # Append-only insert logic
│   │   ├── hash_chain.py               # SHA256 + chain verification
│   │   ├── validator.py                # Contract validation at boundary
│   │   └── errors.py                   # Standard error responses
│   ├── tests/
│   │   ├── test_append_only.py         # Reject mutation attempts
│   │   ├── test_hash_chain.py          # Hash continuity
│   │   ├── test_contract.py            # Schema validation
│   │   └── test_integration.py         # Multi-service writes
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.override.yml     # Local database startup
│
├── ingestion-service/
│   ├── app/
│   │   ├── main.py                     # Camera input / simulator
│   │   ├── camera_input.py             # Real camera OR simulator
│   │   └── trace_generator.py          # Generate unique trace_id
│   ├── requirements.txt
│   └── Dockerfile
│
├── recognition-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── face_detection.py
│   │   └── student_matcher.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── intelligence-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── entry_exit_logic.py
│   │   └── anomaly_detector.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── confidence-service/
│   ├── app/
│   │   ├── main.py
│   │   └── confidence_router.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── human-loop-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── review_queue.py
│   │   └── correction_handler.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── observability-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── event_signals.py            # Transform events for Pravah
│   │   ├── health_monitor.py
│   │   └── failure_emitter.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── backend-integration-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── storage_client.py
│   │   ├── aggregator.py
│   │   └── dashboard_api.py            # Read-only endpoints for UI
│   ├── requirements.txt
│   └── Dockerfile
│
├── dashboard-service/
│   ├── app/
│   │   ├── main.py                     # UI API gateway (read-only)
│   │   ├── review_queue_api.py
│   │   ├── live_monitor_api.py
│   │   └── attendance_api.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── integration-clients/
│   └── backend-services/
│       ├── storage_client_example.py   # Reference: how to call storage API
│       ├── contract_validator.py       # Reference: validate before sending
│       └── README.md                   # Integration guide for new services
│
├── config/
│   ├── .env.template                   # Copy to .env, fill in secrets
│   ├── constants.py                    # Shared constants (API ports, etc)
│   ├── database.yml                    # DB schema for local setup
│   └── docker-compose.yml              # Full stack compose
│
├── docs/
│   ├── CONTRACTS.md                    # Schema reference + examples
│   ├── STORAGE_DESIGN.md               # Hash chain + append-only logic
│   ├── INTEGRATION_GUIDE.md            # How each service integrates
│   ├── FLOW.md                         # End-to-end data flow diagrams
│   └── FAILURE_CASES.md                # What errors mean + how to handle
│
├── infra/
│   ├── docker-compose.yml              # Production-like setup
│   ├── setup-db.sh                     # Initialize PostgreSQL
│   ├── init.sql                        # DB schema
│   └── .env.prod.template              # Production environment
│
└── REVIEW_PACKET.md                    # (Generated at Phase 10) — Proof of execution
```

---

## Naming Rules (Enforce These)

### Services
- All lowercase with hyphens: `storage-service`, `human-loop-service`
- No abbreviations in folder names

### Schema Files
- Filename matches service name + `.schema.json`
- Always singular noun: `ingestion.schema` (not `ingestions`)
- Versioning inside file: `"$schema_version": "1.0"`

### Python Modules
- Snake_case: `trace_generator.py`, `hash_chain.py`
- No underscores for service names; hyphens → underscores in imports only

### API Endpoints
- kebab-case with slash separators: `/store-event`, `/fetch-by-trace`
- Verbs only for actions: POST `/store-event`, GET `/fetch-by-student`

### Test Files
- Prefix with `test_`: `test_append_only.py`, `test_hash_chain.py`
- One test file per module tested

### Config Files
- `.env` for local development (gitignored)
- `.env.template` for team reference (tracked in git)
- `.env.prod.template` for production (tracked in git)

---

## Enforcement

1. **Phase 1 Lock:** Team reviews structure. NO changes accepted after approval.
2. **PR Reviews:** Any folder creation outside this structure is rejected.
3. **CI Checks:** Structure validator runs on every commit.

---

## If You Need to Add Something

**You must:**
1. Propose the new folder/file in issue
2. Get approval from Phase 1 owner (Siddhesh)
3. Update this document
4. Submit as separate PR before merging to main

**You cannot:**
- Create sibling folders outside this structure
- Duplicate services
- Create per-service `.env` files (use central config/)

---

## Quick Commands

Clone and verify structure:
```bash
git clone <repo> hias-system
cd hias-system
# Structure should match above exactly
```

Initialize local environment:
```bash
cp config/.env.template config/.env
# Edit .env with your values
```

Validate structure:
```bash
python scripts/validate_structure.py  # (to be added in Phase 2)
```

---

**Structure is law. Discipline is the system.**
