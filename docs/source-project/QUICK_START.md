# HIAS Team Quick Start — Phase 1 Complete

**Status:** ✅ PHASE 1 LOCKED  
**Repo Location:** `C:\Users\pc44\hias-system`  
**Git Initialized:** ✅ Yes  
**Date:** 2026-04-18  

---

## 📋 What's Ready Now

1. **Unified repo** — Single source of truth for entire team
2. **Directory structure** — Frozen, no deviations allowed
3. **Environment templates** — All service ports + secrets configured
4. **System constants** — API ports, trace format, hash algorithm locked
5. **Service READMEs** — Each service owner knows their responsibility
6. **Git history started** — Team can track changes

---

## 🚀 Team Instructions (Action Items)

### All Team Members
```bash
# Clone the repo
git clone C:\Users\pc44\hias-system hias-system
cd hias-system

# Setup environment
cp config/.env.template config/.env

# Edit .env with your local values
# (if on same machine, most defaults work as-is)
```

### Siddhesh (Phase 2: Contracts + Phase 5-6: Storage)
- [ ] Read `FOLDER_STRUCTURE.md` (enforce with PRs)
- [ ] Create `shared-contracts/schemas/` with 8 JSON schema files (Phase 2)
- [ ] Start implementing `storage-service/` once Phase 2 is done (Phase 5-6)

### Karan (Phase 2-5: Ingestion → Intelligence)
- [ ] Wait for Phase 2 contracts from Siddhesh
- [ ] Setup simulator in `ingestion-service/app/camera_input.py`
- [ ] Implement recognition, intelligence services in sequence

### Vijay (Phase 6: Observability)
- [ ] Wait for Phase 2 contracts for `observability.schema.json`
- [ ] Plan Pravah integration points in `observability-service/`

### Atharva (Phase 7: Integration)
- [ ] Prepare `infra/docker-compose.yml` template
- [ ] Wait for all services ready (Phases 2-6)

### Nikhil + Chandragupta (Phase 8-9: Frontend + Review Queue)
- [ ] Wait for storage API ready (Phase 6)
- [ ] Use `integration-clients/backend-services/storage_client_example.py` as reference

### Vinayak + Rishabh (Phase 10: Testing)
- [ ] Review testing strategy when services are ready
- [ ] Plan ground testing + monitoring

---

## 📁 Key Files to Know

| File | Purpose | Who Reads This |
|------|---------|---|
| `README.md` | System architecture overview | Everyone |
| `FOLDER_STRUCTURE.md` | Naming rules + conventions (frozen) | Everyone + PR reviewers |
| `config/.env.template` | All service ports + DB config | Everyone setting up |
| `config/CONSTANTS.md` | System constants (locked) | Engineers implementing services |
| `docs/PHASE_1_COMPLETION.md` | Phase 1 sign-off + handoff | Phase 1 owner + next phase leads |
| `storage-service/README.md` | Storage service responsibility | Siddhesh, integration teams |
| `ingestion-service/README.md` | Ingestion service responsibility | Karan |
| `recognition-service/README.md` | Recognition service responsibility | Karan |

---

## 🔒 What's Locked (Do NOT Change)

- ✅ Folder structure (no new folders without approval)
- ✅ Service port assignments (8001-8008, 3000)
- ✅ Trace ID format (HIAS-YYYYMMDD-SERVICE-...)
- ✅ Hash algorithm (SHA-256)
- ✅ Naming conventions (kebab-case services, snake_case files)

---

## 🚫 What Will Break During Development

**No PR will merge if:**
- Service code added to wrong folder
- Naming conventions violated
- Contracts not versioned
- `.env` file committed (must be in `.gitignore`)
- Service writes directly to database (must use storage API)

---

## ⏭️ Next Phase (Phase 2: Contracts)

**Owner:** Siddhesh  
**When:** Immediately after Phase 1 complete  
**Task:** Define all 8 contract schemas:
- `ingestion.schema.json`
- `recognition.schema.json`
- `intelligence.schema.json`
- `confidence.schema.json`
- `human_loop.schema.json`
- `storage.schema.json`
- `observability.schema.json`
- `error.schema.json`

**Blocker:** All downstream phases wait for Phase 2 completion.

---

## 💬 Questions?

- Phase 1 structure: Ask Siddhesh
- Service ownership: Check `README.md` phase table
- System constants: Read `config/CONSTANTS.md`
- Integration issues: Check `docs/` (to be filled in later)

---

## ✅ Phase 1 Sign-Off

- Repo location: **C:\Users\pc44\hias-system** ✅
- Structure locked: **Yes** ✅
- Git initialized: **Yes** ✅
- Team ready: **Yes** ✅
- Next phase ready: **Waiting for Siddhesh (Phase 2)** ⏳

---

**Ready to execute. Move to Phase 2.**
