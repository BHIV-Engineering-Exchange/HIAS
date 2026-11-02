# Recognition Service

**Identity Extraction** — Detects faces and matches to student records.

## Responsibility

- Receive ingestion events with images
- Run face detection model
- Match faces to student database
- Extract `student_id` and confidence score
- Create recognition event matching `recognition.schema.json`
- Push to Intelligence Service
- Emit to observability

## Constraints

- ✅ Must preserve `trace_id` from input
- ✅ Must include confidence score (0.0 - 1.0)
- ✅ Must handle "face not found" (student_id = null)
- ❌ Must NOT make routing decisions (that's Confidence Service's job)

## Schema Output

Matches `recognition.schema.json`:
```json
{
  "trace_id": "HIAS-20260418-ING-...",
  "timestamp": "ISO8601",
  "student_id": "STU123 or null",
  "confidence": 0.85,
  "model_version": "v1.2.3"
}
```

## Implementation (Phase 3)

- **Owner:** Karan
- **Entry Point:** `app/main.py`
- **Face Detector:** `app/face_detection.py`
- **Student Matcher:** `app/student_matcher.py`

## Local Execution

```bash
cd recognition-service
pip install -r requirements.txt
python app/main.py
# Runs on http://localhost:8003
```

---

**Accuracy matters. Confidence score must be honest.**
