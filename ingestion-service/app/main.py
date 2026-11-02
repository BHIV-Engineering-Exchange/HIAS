"""HTTP API for ingestion service."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from app.camera_input import CameraEventSimulator
from app.service import IngestionService

app = FastAPI(
    title="HIAS Ingestion Service",
    description="Deterministic camera-input normalization with strict schema enforcement",
    version="1.0.0",
)

ingestion_service = IngestionService()
simulator = CameraEventSimulator()


@app.post("/ingest")
async def ingest(payload: Dict[str, Any]):
    result = ingestion_service.process(payload)
    if result["ok"]:
        return result["event"]
    return JSONResponse(status_code=400, content=result["error"])


@app.post("/simulate")
async def simulate(count: int = Query(20, ge=1, le=200)):
    raw_events = simulator.generate_events(count=count)
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for raw in raw_events:
        result = ingestion_service.process(raw)
        if result["ok"]:
            accepted.append(result["event"])
        else:
            rejected.append(result["error"])

    return {
        "requested": count,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "events": accepted,
        "errors": rejected,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ingestion_service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
