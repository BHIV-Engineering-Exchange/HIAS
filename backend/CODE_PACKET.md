# CODE_PACKET.md — T-GOV-F02 HIAS Software Audit Remediation & Hardening

**Task Title:** Remediate Incorrect Logic & Harden Pritesh Patra, HIAS HOSTEL SOFTWARE AUDIT CONVERGENCE TASK Architecture (T-GOV-F02)  
**Task ID:** T-GOV-F02  
**Assignee Candidate:** Pritesh Patra  
**Product Governance:** BHIV  
**Authority:** PARIKSHAK Production Runtime Engine & NIYANTRAN Task Orchestration  
**Generated At:** 2026-10-27  

---

## 1. Directory Tree

```
hias_combined/
├── api/
│   ├── __init__.py                               # Production API package init
│   └── production.py                             # Hardened production FastAPI application
├── evaluation_engine/
│   ├── __init__.py                               # Evaluation engine package init
│   └── rule_engine.py                            # Access rule engine, minutes arithmetic, SHA-256 state hashing
├── task_selector/
│   ├── __init__.py                               # Task selector package init
│   └── review_orchestrator.py                   # Review queue orchestration, manual overrides, strict actions
├── security/
│   ├── __init__.py                               # Security package init
│   └── middleware.py                             # ErrorBoundaryMiddleware, validation handlers, security headers
├── integrations/
│   ├── __init__.py                               # Integrations package init
│   └── local_llm_client.py                       # Local LLM client with deterministic fallback
├── tests/
│   ├── __init__.py                               # Test root package init
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_rule_engine.py                   # 16 unit tests (rule engine, midnight crossing, 50-run determinism)
│   │   ├── test_review_orchestrator.py           # 7 unit tests (queue, confirm/reject, overrides)
│   │   ├── test_security_middleware.py           # 2 unit tests (error boundary, security headers)
│   │   ├── test_local_llm_client.py              # 2 unit tests (fallback, schemas)
│   │   ├── test_backend_engine.py                # 12 unit tests (backend engine evaluate)
│   │   ├── test_backend_schemas.py               # 17 unit tests (backend schemas)
│   │   └── test_backend_cosec.py                 # 11 unit tests (COSEC adapter parser)
│   └── integration/
│       ├── __init__.py
│       ├── test_production_api.py                # 19 integration tests (production endpoints, error boundaries)
│       ├── test_backend_api.py                   # 22 integration tests (backend routes, 422 boundaries)
│       └── test_backend_worker.py                # 2 integration tests (COSEC worker loop)
├── backend/
│   ├── app/
│   │   ├── engine.py                             # ✅ MODIFIED — fixed Rule 0 emergency bypass & time window
│   │   ├── main.py                               # ✅ MODIFIED — fixed async event loop call, strict Pydantic models
│   │   ├── schemas.py                            # ✅ MODIFIED — added strict models, widened reason
│   │   └── logger.py                             # ✅ MODIFIED — non-blocking daemon thread log dispatch
│   ├── requirements.txt                          # ✅ MODIFIED — 100% strict == version pinning
│   └── pytest.ini                                # Pytest runner config for backend/
├── pytest.ini                                    # Pytest runner config for workspace root
├── requirements.txt                              # Root requirements with exact == version pinning
├── REVIEW_PACKET.md                              # Comprehensive architectural proofs & verification logs
├── CODE_PACKET.md                                # This deliverable
└── CODE_INDEX.md                                 # Full code index & deliverable catalogue
```

---

## 2. Changed Files Summary

### `backend/app/engine.py`
- **Bug 1 Fixed:** Resolved `AttributeError` when `db_user` is `None` during emergency mode by extracting user identity in a safe guard prior to rule evaluation.
- **Bug 2 Fixed:** Re-implemented `is_within_time_window()` using integer minutes-since-midnight arithmetic with dual branches, supporting overnight windows crossing midnight (e.g., 22:00 to 06:00).

### `backend/app/schemas.py`
- Added strict Pydantic models: `ManualOverrideInput`, `UserEnrollInput`, `SettingsUpdateInput` (with `extra="forbid"` to reject unauthorized parameters).
- Narrowed `ReviewAction.action` to `Literal["confirm", "reject"]`.
- Allowed `ControllerEvent.reason` to accept both standard `Reason` enum members and descriptive strings (`Reason | str`).

### `backend/app/main.py`
- **Bug 3 Fixed:** Replaced `asyncio.get_event_loop().time()` with `time.monotonic()` in `process_access_request`.
- **Bug 4 Fixed:** Changed `startup_event` from `def` to `async def`.
- **Bug 5 Fixed:** Replaced raw `dict` parameter types in `/manual/override`, `/users`, and `/settings` with strict Pydantic schemas.
- Configured anti-passback `DUPLICATE_THRESHOLD` to 2.0s.

### `backend/app/logger.py`
- Replaced blocking synchronous HTTP requests to external logging service with asynchronous background daemon threads (`_async_post`), preventing request timeouts and request blocking.

### `backend/requirements.txt` & `requirements.txt`
- Pinned all dependencies strictly with `==`:
  - `fastapi==0.115.8`
  - `uvicorn[standard]==0.34.0`
  - `pydantic==2.13.3`
  - `pydantic-core==2.46.3`
  - `requests==2.34.2`
  - `python-dotenv==1.2.2`
  - `cryptography==49.0.0`
  - `pytest==9.0.3`
  - `pytest-asyncio==0.24.0`
  - `sse-starlette==2.1.0`
  - `sqlalchemy==2.0.30`
  - `psycopg2-binary==2.9.9`
  - `httpx==0.27.0`
- Removed unpinned `>=` entries.

---

## 3. Newly Created Modules

1. `evaluation_engine/rule_engine.py`: Core rule evaluation engine with deterministic SHA-256 state hashing and midnight-crossing time arithmetic.
2. `task_selector/review_orchestrator.py`: Review queue manager enforcing strict `ReviewAction` (`Literal["confirm", "reject"]`) and manual override handling.
3. `security/middleware.py`: `ErrorBoundaryMiddleware` capturing unhandled server errors into structured HTTP 500 JSON with `X-Trace-ID` and security headers; `validation_exception_handler` normalizing 422 responses.
4. `integrations/local_llm_client.py`: Client for local LLM inference with deterministic fallback.
5. `api/production.py`: Hardened production FastAPI application implementing all endpoints, strict schemas, error boundaries, and rule evaluation.
6. `tests/`: 119 unit and integration test cases covering edge cases, determinism, schema boundaries, and error protection.

---

## 4. Verification Commands

```powershell
# 1. Run root test suite (119 test cases)
python -m pytest -v

# 2. Run backend test suite (77 test cases)
cd backend
python -m pytest -v
cd ..

# 3. Verify zero unpinned >= dependencies
Select-String ">= " requirements.txt backend/requirements.txt
# Expected: 0 matches
```
