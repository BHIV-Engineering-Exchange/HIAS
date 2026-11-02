# Shared Contracts — Single Source of Truth

**All services import schemas from here. Breaking contracts is failure.**

---

## Contract Map

```
ingestion.schema.json
    ↓ (trace_id generated)
recognition.schema.json
    ↓ (student_id + confidence extracted)
intelligence.schema.json
    ↓ (ENTRY/EXIT logic applied)
confidence.schema.json
    ↓ (routing decision: AUTO/REVIEW/REJECT)
    ├→ AUTO/CORRECTED → storage.schema.json
    │                    ↓
    │                  FINAL TRUTH (Append-Only, Hash-Linked)
    │
    └→ REVIEW → human-loop.schema.json
        ↓ (operator correction)
        → storage.schema.json
        ↓
        FINAL TRUTH
```

**Parallel Track:**
- All services emit: `observability.schema.json` (metrics, health, events) → Pravah
- All services can emit: `error.schema.json` (failures, contract violations) → Pravah + Alerting

---

## Schema Details

| Schema | Owner | Responsibility | Output To |
|--------|-------|-----------------|-----------|
| **ingestion** | Ingestion Service | Camera input → trace_id generation | Recognition Service |
| **recognition** | Recognition Service | Image → face detection → student_id | Intelligence Service |
| **intelligence** | Intelligence Service | Events → ENTRY/EXIT logic | Confidence Service |
| **confidence** | Confidence Service | Routing decision (AUTO/REVIEW/REJECT) | Storage OR Human Loop |
| **human-loop** | Human Loop Service | Operator correction action | Storage Service |
| **storage** | Storage Service | FINAL event record (immutable, hash-linked) | Database (PostgreSQL) |
| **observability** | All Services | Metrics, health, events for Pravah | Observability Service |
| **error** | All Services | Failures, contract violations | Observability Service + Alerts |

---

## Critical Rules (NON-NEGOTIABLE)

✅ **MUST DO:**
- ✓ Every event carries `trace_id` throughout pipeline
- ✓ Every service validates incoming data against **source** schema before processing
- ✓ Every service outputs data matching **destination** schema
- ✓ Storage service receives ONLY `storage.schema.json` payload
- ✓ No direct database writes — **all writes go through Storage API**

❌ **MUST NOT:**
- ✗ Modify contracts without approval (leads to pipeline breakage)
- ✗ Add optional fields that downstream services don't expect
- ✗ Skip schema validation
- ✗ Create per-service schema variants
- ✗ Store data that didn't go through storage.schema.json
- ✗ Update stored records (append-only rule)

---

## Schema Validation

Each service MUST:

```python
from jsonschema import validate
import json

# Load schema
with open('shared-contracts/schemas/storage.schema.json') as f:
    storage_schema = json.load(f)

# Validate before write
try:
    validate(instance=incoming_event, schema=storage_schema)
except ValidationError as e:
    # Reject and emit error signal
    emit_error(error_code=ERR_INVALID_SCHEMA, trace_id=...)
    raise
```

---

## Trace ID Format

```
HIAS-20260418-a1b2c3d4-000001
└─┬─┘ └──┬──┘ └──┬──┘ └──┬──┘
  │      │       │       └─ Sequence number (6 digits, incremental)
  │      │       └─────────── SHA256 prefix (8 hex chars)
  │      └────────────────── Timestamp (YYYYMMDD)
  └───────────────────────── System ID (HIAS)
```

Ingestion service generates. Persists immutably through entire pipeline.

---

## Integration Points

**Who Writes To Storage?**
1. Confidence Service → if routing = AUTO or REJECT
2. Human Loop Service → if operator corrects

**Who Reads From Storage?**
1. Backend Integration Service → aggregates for dashboard
2. Dashboard Service → serves UI

**Who Emits Observability Signals?**
All services → Pravah (for metrics, health, audit)

---

## Quick Start: New Service Integration

1. **Read** the relevant input schema (e.g., `intelligence.schema.json`)
2. **Validate** incoming data against it
3. **Process** and enrich
4. **Output** data matching next schema in pipeline
5. **Validate** output before sending
6. **Emit** observability signals for all operations
7. **Error** handler → emit `error.schema.json` to Pravah

---

## Schema Updates (Policy)

**Breaking Changes (Require Team Approval):**
- Removing required fields
- Changing field types
- Renaming fields

**Safe Changes (Document in git):**
- Adding new optional fields
- Tightening validation (more restrictive patterns)
- Clarifying descriptions

**Process:**
1. Create branch: `schemas/update-{name}`
2. Update schema file
3. Update this README
4. Notify affected service owners
5. Merge after approval from Siddhesh (Storage Owner)

---

## Validation Endpoints (Phase 7)

Storage Service exposes schema validation:

```
POST /validate?schema=storage
{
  "event": {...}
}
```

All services MUST use this before writing critical events.

---

## Debugging Guide

**Trace a specific event:**
```
1. Get trace_id from dashboard
2. POST /fetch-by-trace?trace_id=HIAS-...
3. View complete event history (all transformations)
4. Check hash chain integrity
```

**Replay event through services:**
```
1. Fetch event from storage
2. Inject back at ingestion service with same trace_id
3. Compare outputs with original (should be identical)
```

---

**Owner:** Siddhesh  
**Last Updated:** 2026-04-18  
**Status:** Phase 2 Complete ✅
