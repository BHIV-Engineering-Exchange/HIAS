# HIAS Review Packet

## Scope

This packet proves the current HIAS system is stable across the core pipeline and the MongoDB Atlas storage gateway:

- ingestion layer
- recognition layer
- intelligence layer
- confidence routing
- duplicate prevention
- structured failure contract
- append-only storage and hash chaining

Execution date: 2026-04-29

## Non-Negotiable Rules Status

- No breaking contract: PASS
- No skipping steps: PASS
- No direct DB writes: PASS
- No random behavior: PASS
- No missing trace_id: PASS
- No mutable storage: PASS
- No bypassing `/store-event`: PASS

## Entry Point

The storage gateway is the single write entry point:

`POST /store-event`

Contract input: `storage.schema.json`

Response: `{ trace_id, event_id, hash, prev_hash, status }`

## Core Flow

1. `ingestion-service/app/main.py` - ingest and normalize camera payloads
2. `recognition-service/app/main.py` - detect face and assign confidence/student_id
3. `storage-service/app/main.py` - validate final events, append to MongoDB Atlas, and update chain state

## Live Flow

- Ingestion: `http://127.0.0.1:8002`
- Recognition: `http://127.0.0.1:8003`
- Intelligence: `http://127.0.0.1:8004`
- Storage: `http://127.0.0.1:8005`

Storage write path:

`final event -> POST /store-event -> events + chain_state`

## What Was Built

- Deterministic pipeline with trace continuity
- Confidence routing with `AUTO / REVIEW / REJECT`
- Edge-case handling for duplicates and impossible transitions
- MongoDB Atlas append-only storage gateway
- Hash chain linkage with `prev_hash -> hash`
- Contract validation using `storage.schema.json`

## Failure Cases

1. Invalid storage payload - rejected with structured failure response
2. Duplicate `trace_id` - rejected by append-only guard
3. Missing required field - rejected by schema validation
4. Bad DB config - storage startup fails fast, no partial write

## Proof

### Pipeline proof
- 30-event mixed run completed successfully
- `AUTO`, `REVIEW`, and `REJECT` outputs observed
- duplicate and anomaly cases handled without crash

### Storage proof
- Atlas database: `hias`
- Collections: `events`, `chain_state`
- First stored trace: `HIAS-20260429-abcdef12-000001`
- Stored event hash: `3d46fac78cf5c65a60823c3ed58039256abe93eb01c8f000188200ea80ed96f9`
- Chain head updated in `chain_state`

### Phase 8 endpoint contract

`POST /store-event`

Sample payload:

```json
{
  "trace_id": "HIAS-20260429-abcdef12-000001",
  "timestamp": "2026-04-29T13:15:00Z",
  "student_id": "STU123456",
  "event": "ENTRY",
  "confidence": 0.9,
  "status": "AUTO",
  "source_service": "confidence_service",
  "camera_id": "GATE-MAIN",
  "zone": "GATE_MAIN"
}
```

`GET /fetch-by-trace?trace_id=<trace_id>`

`GET /fetch-by-student?student_id=<student_id>&date=YYYY-MM-DD&status=AUTO`

### Atlas proof events

- `confidence_service` wrote an `AUTO` event to `events`
- `human_loop_service` can write `CORRECTED` events through the same contract

## Readiness

- Core pipeline is stable
- Storage gateway is live and append-only
- Hash chain is functioning
- Contract boundaries are enforced
- Docs and runtime are now aligned on storage port `8005`
