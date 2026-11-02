# Integration Guide — Writing to HIAS Storage

## Rule
All services write through `POST /store-event` on the storage-service.  
No direct DB access. No exceptions.

## Steps

1. Build payload matching `shared-contracts/schemas/storage.schema.json`
2. Validate locally using `contract_validator.py`
3. POST to `http://127.0.0.1:8005/store-event`
4. Check response `status` field: `ACCEPTED` or `REJECTED`

## Required Fields

| Field | Type | Example |
|---|---|---|
| `trace_id` | string | `HIAS-20260429-abcdef12-000001` |
| `timestamp` | ISO8601 | `2026-04-29T13:15:00Z` |
| `student_id` | string | `STU123456` |
| `event` | `ENTRY` or `EXIT` | `ENTRY` |
| `confidence` | float 0–1 | `0.92` |
| `status` | `AUTO/REVIEW/REJECT/CORRECTED` | `AUTO` |
| `source_service` | `confidence_service` or `human_loop_service` | `confidence_service` |

## Response

```json
{
  "trace_id": "HIAS-20260429-abcdef12-000001",
  "event_id": "<uuid>",
  "hash": "<sha256>",
  "prev_hash": "<sha256 or 000...0>",
  "status": "ACCEPTED"
}
```

## Reference Files

- `storage_client_example.py` — full working example
- `contract_validator.py` — local pre-validation
