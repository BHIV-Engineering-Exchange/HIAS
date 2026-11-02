"""HTTP API for intelligence service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.service import IntelligenceService
from app.storage_client import StorageClient

app = FastAPI(
    title="HIAS Intelligence Service",
    description="Deterministic event interpretation and confidence routing",
    version="1.0.0",
)

storage_client = StorageClient()
intelligence_service = IntelligenceService(storage_client=storage_client)


class IntelligenceRequest(BaseModel):
    recognition_event: Dict[str, Any]
    context: Optional[Dict[str, Any]] = Field(default=None)


@app.post("/process")
async def process(request: IntelligenceRequest):
    result = intelligence_service.process(
        recognition_event=request.recognition_event,
        context=request.context,
    )
    if not result["ok"]:
        status_code = (
            503
            if result["error"].get("error_type")
            in ("SERVICE_UNAVAILABLE", "TIMEOUT")
            else 400
        )
        return JSONResponse(
            status_code=status_code,
            content=result["error"],
        )

    storage_result = storage_client.store_event(result["storage_event"])
    response_data = {
        "intelligence_event": result["intelligence_event"],
        "confidence_event": result["confidence_event"],
        "storage_event": result["storage_event"],
        "final_event": result["final_event"],
        "status": result["status"],
        "storage_result": storage_result,
    }

    if storage_result.get("success"):
        return response_data

    storage_status = storage_result.get("status", "UNKNOWN")

    # Unknown/rejected identities are intentionally not persisted.
    if storage_status == "SKIPPED":
        return response_data

    # Do not report successful processing when persistence failed.
    status_code = (
        503
        if storage_status in ("UNREACHABLE", "TIMEOUT")
        else 502
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "STORAGE_PERSISTENCE_FAILED",
            "message": "Intelligence event could not be persisted.",
            **response_data,
        },
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "intelligence_service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
