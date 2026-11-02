# System Constants

Shared constants across all HIAS services. Do NOT override these without explicit approval.

## Service Ports

```python
STORAGE_SERVICE_PORT = 8001
INGESTION_SERVICE_PORT = 8002
RECOGNITION_SERVICE_PORT = 8003
INTELLIGENCE_SERVICE_PORT = 8004
CONFIDENCE_SERVICE_PORT = 8005
HUMAN_LOOP_SERVICE_PORT = 8006
OBSERVABILITY_SERVICE_PORT = 8007
BACKEND_INTEGRATION_SERVICE_PORT = 8008
DASHBOARD_SERVICE_PORT = 3000
```

## Service Hostnames

```python
STORAGE_SERVICE_URL = "http://storage-service:8001"
INGESTION_SERVICE_URL = "http://ingestion-service:8002"
RECOGNITION_SERVICE_URL = "http://recognition-service:8003"
INTELLIGENCE_SERVICE_URL = "http://intelligence-service:8004"
CONFIDENCE_SERVICE_URL = "http://confidence-service:8005"
HUMAN_LOOP_SERVICE_URL = "http://human-loop-service:8006"
OBSERVABILITY_SERVICE_URL = "http://observability-service:8007"
BACKEND_INTEGRATION_SERVICE_URL = "http://backend-integration-service:8008"
```

## API Paths (Storage Service — The Gateway)

```
POST   /store-event              # Write to immutable storage
GET    /fetch-by-trace           # Retrieve by trace_id
GET    /fetch-by-student         # Retrieve by student_id
GET    /health                   # Health check
GET    /hash-verify              # Chain integrity check
```

## Event Status Constants

```python
STATUS_AUTO = "AUTO"           # Automatically accepted by confidence
STATUS_REVIEW = "REVIEW"       # Routed to human review queue
STATUS_REJECTED = "REJECTED"   # Manually rejected
STATUS_CORRECTED = "CORRECTED" # Manually corrected + updated
```

## Event Type Constants

```python
EVENT_ENTRY = "ENTRY"          # Student entered
EVENT_EXIT = "EXIT"            # Student exited
EVENT_ANOMALY = "ANOMALY"      # Anomaly detected
EVENT_CORRECTION = "CORRECTION" # Manual correction event
```

## Confidence Thresholds

```python
MIN_RECOGNITION_CONFIDENCE = 0.70      # Face recognition must be >= 70%
REVIEW_THRESHOLD = 0.65                # Route to review if confidence < 65%
ANOMALY_DETECTION_THRESHOLD = 0.85     # Flag anomaly if confidence > 85% but unusual
FINAL_ACCEPT_THRESHOLD = 0.95          # Auto-accept without review if >= 95%
```

## Trace ID Format

```
Prefix: HIAS
Format: HIAS-<YYYYMMDD>-<SERVICE>-<TIMESTAMP>-<RANDOM_32_HEX>
Example: HIAS-20260418-ING-1713437451203-a7f3e9c2b1d5f8a0c4e6b9d2f1a5c8e0
```

## Database Schema Version

```
SCHEMA_VERSION = "1.0"
SCHEMA_COMPATIBILITY = "1.0"  # Minimum compatible version
```

## Hash Chain Constants

```python
HASH_ALGORITHM = "sha256"
PREV_HASH_INITIAL = "0000000000000000000000000000000000000000000000000000000000000000"  # 64 zeros
```

## Timeouts (milliseconds)

```python
API_REQUEST_TIMEOUT = 30000         # 30 seconds
DATABASE_QUERY_TIMEOUT = 10000      # 10 seconds
INTER_SERVICE_TIMEOUT = 5000        # 5 seconds for service-to-service calls
```

## Pagination

```python
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000
MIN_PAGE_SIZE = 1
```

## Retry Policy

```python
MAX_RETRIES = 3
RETRY_BACKOFF_MS = 500              # exponential backoff: 500ms, 1s, 2s
```

## Do Not Edit Without Approval

These constants define the contract boundaries. Changing any of these without team agreement breaks integration.

**Last Updated:** 2026-04-18  
**Approved By:** Team Lead
