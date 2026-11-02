# Ingestion Service

**System Entry Point** — Captures camera input or simulator events and generates trace_id.

## Responsibility

- Read camera input (real or simulator)
- Generate unique `trace_id` for each event
- Create ingestion event matching `ingestion.schema.json`
- Push to Recognition Service
- Log to observability service

## Constraints

- ✅ Must generate `trace_id` that stays with event forever
- ✅ Must validate ingestion payload before forwarding
- ❌ Must NOT write directly to storage (goes through full pipeline)

## Schema

Input: Camera frame + student zone info

Output matches `ingestion.schema.json`:
```json
{
  "trace_id": "HIAS-20260418-ING-...",
  "timestamp": "ISO8601",
  "image_data": "base64_or_path",
  "zone_id": "zone_name",
  "camera_id": "camera_serial"
}
```

## Implementation (Phase 2)

- **Owner:** Karan
- **Entry Point:** `app/main.py`
- **Camera Simulator:** `app/camera_input.py` (for local testing)
- **Trace Generator:** `app/trace_generator.py`

## Local Execution

```bash
cd ingestion-service
pip install -r requirements.txt
INGESTION_CAMERA_MODE=simulator python app/main.py
# Runs on http://localhost:8002
```

## Dependencies

- Depends on: Recognition Service (downstream)
- Used by: Observability Service (for tracing)

---

**This service starts the trace. Never lose trace_id.**
