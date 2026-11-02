"""MongoDB Atlas connection helpers for the storage service."""

from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection

from app.config import settings

logger = logging.getLogger(__name__)

client = MongoClient(
    settings.DATABASE_URL,
    serverSelectionTimeoutMS=settings.CONNECTION_TIMEOUT * 1000,
    retryWrites=True,
)

database = client[settings.MONGODB_DB_NAME]
events_collection: Collection = database[settings.MONGODB_EVENTS_COLLECTION]
chain_state_collection: Collection = database[settings.MONGODB_CHAIN_STATE_COLLECTION]


def get_events_collection() -> Collection:
    return events_collection


def get_chain_state_collection() -> Collection:
    return chain_state_collection


def get_db_session() -> MongoClient:
    return client


def init_db() -> None:
    try:
        logger.info("Initializing MongoDB indexes...")
        client.admin.command("ping")

        events_collection.create_index([("trace_id", ASCENDING)], unique=True, name="uniq_trace_id")
        events_collection.create_index([("hash", ASCENDING)], unique=True, name="uniq_hash")
        events_collection.create_index([("student_id", ASCENDING), ("timestamp", DESCENDING)], name="student_timestamp_idx")
        events_collection.create_index([("timestamp", DESCENDING)], name="timestamp_idx")
        events_collection.create_index([("status", ASCENDING)], name="status_idx")
        events_collection.create_index([("prev_hash", ASCENDING)], name="prev_hash_idx")

        chain_state_collection.update_one(
            {"_id": "global"},
            {
                "$setOnInsert": {
                    "_id": "global",
                    "last_hash": "0" * 64,
                    "last_trace_id": None,
                    "updated_at": None,
                }
            },
            upsert=True,
        )

        logger.info("MongoDB storage layer initialized")
    except Exception as exc:
        logger.error(f"MongoDB initialization failed: {exc}")
        raise


def drop_db() -> None:
    database.drop_collection(settings.MONGODB_EVENTS_COLLECTION)
    database.drop_collection(settings.MONGODB_CHAIN_STATE_COLLECTION)


def get_engine():
    return {
        "database": settings.MONGODB_DB_NAME,
        "events_collection": settings.MONGODB_EVENTS_COLLECTION,
        "chain_state_collection": settings.MONGODB_CHAIN_STATE_COLLECTION,
    }


def get_db():
    yield client
