"""HIAS Storage Service - MongoDB Atlas append-only truth layer."""

from __future__ import annotations

from datetime import datetime
import logging
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.database import init_db
from app.hash_chain import HashChain
from app.validator import SchemaValidator
from app.writer import StorageWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HIAS Storage Service",
    description="Immutable append-only event storage with hash chain verification",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

validator = SchemaValidator()
hash_chain = HashChain()
writer: Optional[StorageWriter] = None


class StoreEventResponse(BaseModel):
    trace_id: str
    event_id: str
    hash: str
    prev_hash: Optional[str]
    status: str
    reason: Optional[str] = None


class FetchEventResponse(BaseModel):
    trace_id: str
    event_id: str
    student_id: str
    event: str
    confidence: float
    status: str
    timestamp: str
    hash: str
    prev_hash: Optional[str]


class EventListResponse(BaseModel):
    events: List[FetchEventResponse]
    total_count: int
    trace_count: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    database: str



def _event_to_response(event: dict) -> FetchEventResponse:
    return FetchEventResponse(
        trace_id=event.get("trace_id"),
        event_id=str(event.get("event_id") or event.get("_id")),
        student_id=event.get("student_id"),
        event=event.get("event"),
        confidence=float(event.get("confidence", 0.0)),
        status=event.get("status"),
        timestamp=event["timestamp"].isoformat() if event.get("timestamp") else "",
        hash=event.get("hash"),
        prev_hash=event.get("prev_hash"),
    )


@app.on_event("startup")
async def startup_event():
    global writer
    logger.info("Initializing Storage Service...")
    init_db()
    writer = StorageWriter()
    logger.info("Storage Service initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Storage Service shutting down...")


@app.post("/store-event", response_model=StoreEventResponse)
async def store_event(payload: dict):
    try:
        logger.info("Validating event: %s", payload.get("trace_id", "unknown"))
        is_valid, validation_error = validator.validate_storage_event(payload)

        if not is_valid:
            return StoreEventResponse(
                trace_id=payload.get("trace_id", "UNKNOWN"),
                event_id="",
                hash="",
                prev_hash=None,
                status="REJECTED",
                reason=f"Schema validation failed: {validation_error}",
            )

        if writer is None:
            raise HTTPException(status_code=503, detail="Storage service not initialized")

        result = writer.append_event(payload)
        if result["success"]:
            return StoreEventResponse(
                trace_id=result["trace_id"],
                event_id=result["event_id"],
                hash=result["hash"],
                prev_hash=result["prev_hash"],
                status="ACCEPTED",
                reason=None,
            )

        return StoreEventResponse(
            trace_id=payload.get("trace_id", "UNKNOWN"),
            event_id="",
            hash="",
            prev_hash=None,
            status="REJECTED",
            reason=result["error"],
        )
    except Exception as exc:
        logger.error("Store event failed: %s", exc)
        return StoreEventResponse(
            trace_id=payload.get("trace_id", "UNKNOWN"),
            event_id="",
            hash="",
            prev_hash=None,
            status="REJECTED",
            reason=f"Internal error: {str(exc)}",
        )


@app.get("/fetch-by-trace", response_model=EventListResponse)
async def fetch_by_trace(trace_id: str = Query(..., description="Trace ID to fetch")):
    try:
        if writer is None:
            raise HTTPException(status_code=503, detail="Storage service not initialized")

        events = writer.fetch_by_trace(trace_id)
        if not events:
            return EventListResponse(events=[], total_count=0, trace_count=0)

        return EventListResponse(
            events=[_event_to_response(event) for event in events],
            total_count=len(events),
            trace_count=1,
        )
    except Exception as exc:
        logger.error("Fetch by trace failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/fetch-by-student", response_model=EventListResponse)
async def fetch_by_student(
    student_id: str = Query(..., description="Student ID"),
    date: Optional[str] = Query(None, description="Date filter (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Event status filter"),
):
    try:
        if writer is None:
            raise HTTPException(status_code=503, detail="Storage service not initialized")

        events = writer.fetch_by_student(student_id, date, status)
        return EventListResponse(events=[_event_to_response(event) for event in events], total_count=len(events))
    except Exception as exc:
        logger.error("Fetch by student failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service="storage-service",
        timestamp=datetime.utcnow().isoformat(),
        database=settings.MONGODB_DB_NAME,
    )


@app.get("/stats")
async def get_stats():
    try:
        if writer is None:
            raise HTTPException(status_code=503, detail="Storage service not initialized")
        return writer.get_stats()
    except Exception as exc:
        logger.error("Stats fetch failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/")
async def root():
    return {
        "service": "HIAS Storage Service",
        "version": "1.0.0",
        "description": "Append-only, hash-linked immutable event storage",
        "endpoints": {
            "store_event": {"method": "POST", "path": "/store-event"},
            "fetch_by_trace": {"method": "GET", "path": "/fetch-by-trace?trace_id=..."},
            "fetch_by_student": {"method": "GET", "path": "/fetch-by-student?student_id=..."},
            "health": {"method": "GET", "path": "/health"},
            "stats": {"method": "GET", "path": "/stats"},
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.SERVICE_HOST, port=settings.SERVICE_PORT)
