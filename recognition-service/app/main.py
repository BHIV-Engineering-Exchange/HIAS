"""HTTP API for recognition service."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.service import RecognitionService

app = FastAPI(
    title="HIAS Recognition Service",
    description="Deterministic student matching with strict contract enforcement",
    version="1.0.0",
)

recognition_service = RecognitionService()


@app.post("/recognize")
async def recognize(ingestion_event: Dict[str, Any]):
    result = recognition_service.process(ingestion_event)
    if result["ok"]:
        return result["event"]
    return JSONResponse(status_code=400, content=result["error"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "recognition_service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
