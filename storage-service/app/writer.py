"""MongoDB-backed append-only storage writer."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.database import chain_state_collection, client, events_collection
from app.hash_chain import HashChain
from app.validator import SchemaValidator

logger = logging.getLogger(__name__)


class StorageWriter:
    """Append-only storage writer for MongoDB Atlas."""

    def __init__(self, session_factory=None):
        self.hash_chain = HashChain()
        self.validator = SchemaValidator()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_timestamp(timestamp_value: Optional[object]) -> datetime:
        if not timestamp_value:
            return StorageWriter._utc_now()
        if isinstance(timestamp_value, datetime):
            if timestamp_value.tzinfo is None:
                return timestamp_value.replace(tzinfo=timezone.utc)
            return timestamp_value.astimezone(timezone.utc)
        if isinstance(timestamp_value, str):
            normalized = timestamp_value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        raise TypeError(f"Unsupported timestamp type: {type(timestamp_value)}")

    def _get_last_hash(self) -> str:
        chain_state = chain_state_collection.find_one({"_id": "global"})
        if chain_state and chain_state.get("last_hash"):
            return chain_state["last_hash"]
        return self.hash_chain.GENESIS_HASH

    def _build_document(self, event_data: dict, event_id: str, current_hash: str, prev_hash: str) -> dict:
        return {
            "_id": event_id,
            "event_id": event_id,
            "trace_id": event_data["trace_id"],
            "timestamp": self._parse_timestamp(event_data.get("timestamp")),
            "student_id": event_data["student_id"],
            "event": event_data["event"],
            "confidence": float(event_data["confidence"]),
            "status": event_data["status"],
            "source_service": event_data["source_service"],
            "camera_id": event_data.get("camera_id"),
            "zone": event_data.get("zone"),
            "anomaly_flags": event_data.get("anomaly_flags", []),
            "metadata": event_data.get("metadata", {}),
            "hash": current_hash,
            "prev_hash": prev_hash,
            "created_at": self._utc_now(),
        }

    @staticmethod
    def _format_timestamp_for_hash(timestamp_value: Optional[object]) -> Optional[str]:
        if timestamp_value is None:
            return None
        if isinstance(timestamp_value, str):
            try:
                dt = StorageWriter._parse_timestamp(timestamp_value)
                timestamp_value = dt
            except Exception:
                return timestamp_value if timestamp_value.endswith("Z") else timestamp_value.replace("+00:00", "Z")

        if isinstance(timestamp_value, datetime):
            timestamp_utc = (
                timestamp_value.astimezone(timezone.utc)
                if timestamp_value.tzinfo
                else timestamp_value.replace(tzinfo=timezone.utc)
            )
            if timestamp_utc.microsecond == 0:
                return timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            if timestamp_utc.microsecond % 1000 == 0:
                frac = f"{timestamp_utc.microsecond // 1000:03d}"
            else:
                frac = f"{timestamp_utc.microsecond:06d}".rstrip("0")
            return f"{timestamp_utc.strftime('%Y-%m-%dT%H:%M:%S')}.{frac}Z"

        return str(timestamp_value)

    def append_event(self, event_data: dict) -> Dict:
        trace_id = event_data.get("trace_id", "UNKNOWN")
        try:
            is_valid, validation_error = self.validator.validate_storage_event(event_data)
            if not is_valid:
                return {"success": False, "error": validation_error, "trace_id": trace_id}

            if events_collection.find_one({"trace_id": trace_id}, {"_id": 1}):
                return {
                    "success": False,
                    "error": "Event with this trace_id already exists (append-only constraint)",
                    "trace_id": trace_id,
                }

            prev_hash = self._get_last_hash()
            event_for_hash = {
                key: value
                for key, value in event_data.items()
                if key not in {"hash", "prev_hash", "created_at", "event_id"}
            }
            if "anomaly_flags" in event_for_hash and not event_for_hash["anomaly_flags"]:
                del event_for_hash["anomaly_flags"]
            if "metadata" in event_for_hash and not event_for_hash["metadata"]:
                del event_for_hash["metadata"]
            if "timestamp" in event_for_hash:
                event_for_hash["timestamp"] = self._format_timestamp_for_hash(event_for_hash["timestamp"])
            current_hash = self.hash_chain.generate_hash(prev_hash, event_for_hash)
            event_id = str(uuid.uuid4())
            document = self._build_document(event_data, event_id, current_hash, prev_hash)

            with client.start_session() as session:
                with session.start_transaction():
                    events_collection.insert_one(document, session=session)
                    chain_state_collection.find_one_and_update(
                        {"_id": "global"},
                        {
                            "$set": {
                                "last_hash": current_hash,
                                "last_trace_id": trace_id,
                                "updated_at": self._utc_now(),
                            },
                            "$setOnInsert": {"_id": "global"},
                        },
                        upsert=True,
                        return_document=ReturnDocument.AFTER,
                        session=session,
                    )

            logger.info("Stored event %s with hash %s", trace_id, current_hash)
            return {
                "success": True,
                "event_id": event_id,
                "trace_id": trace_id,
                "hash": current_hash,
                "prev_hash": prev_hash,
            }

        except DuplicateKeyError:
            return {
                "success": False,
                "error": "Event with this trace_id already exists (append-only constraint)",
                "trace_id": trace_id,
            }
        except PyMongoError as exc:
            logger.error("Mongo write error: %s", exc)
            return {"success": False, "error": str(exc), "trace_id": trace_id}
        except Exception as exc:
            logger.error("Unexpected write error: %s", exc)
            return {"success": False, "error": str(exc), "trace_id": trace_id}

    def fetch_by_trace(self, trace_id: str) -> List[dict]:
        return list(events_collection.find({"trace_id": trace_id}).sort("created_at", 1))

    def fetch_by_student(
        self,
        student_id: str,
        date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[dict]:
        query: Dict[str, object] = {"student_id": student_id}

        if status:
            query["status"] = status

        if date:
            start = datetime.fromisoformat(f"{date}T00:00:00+00:00")
            end = start + timedelta(days=1)
            query["timestamp"] = {"$gte": start, "$lt": end}

        return list(events_collection.find(query).sort("created_at", -1))

    def verify_chain_integrity(self) -> Dict:
        try:
            events = list(events_collection.find({}).sort("created_at", 1))
            if not events:
                return {"valid": True, "total_events": 0}

            events_dict = []
            for event in events:
                event_dict = {
                    "trace_id": event.get("trace_id"),
                    "timestamp": self._format_timestamp_for_hash(event.get("timestamp")),
                    "student_id": event.get("student_id"),
                    "event": event.get("event"),
                    "confidence": event.get("confidence"),
                    "status": event.get("status"),
                    "source_service": event.get("source_service"),
                    "hash": event.get("hash"),
                    "prev_hash": event.get("prev_hash"),
                }
                if event.get("camera_id") is not None:
                    event_dict["camera_id"] = event.get("camera_id")
                if event.get("zone") is not None:
                    event_dict["zone"] = event.get("zone")
                if event.get("anomaly_flags"):
                    event_dict["anomaly_flags"] = event.get("anomaly_flags")
                if event.get("metadata"):
                    event_dict["metadata"] = event.get("metadata")
                events_dict.append(event_dict)

            is_valid, error = self.hash_chain.verify_full_chain(events_dict)
            return {"valid": is_valid, "total_events": len(events), "error": error}
        except Exception as exc:
            logger.error("Error verifying chain: %s", exc)
            return {"valid": False, "total_events": 0, "error": str(exc)}

    def get_stats(self) -> Dict:
        try:
            total_events = events_collection.count_documents({})
            total_students = len([student for student in events_collection.distinct("student_id") if student])
            last_event = events_collection.find_one({}, sort=[("created_at", -1)])
            integrity = self.verify_chain_integrity()

            return {
                "total_events": total_events,
                "total_students": total_students,
                "last_event_timestamp": last_event["timestamp"].isoformat() if last_event and last_event.get("timestamp") else None,
                "hash_chain_verified": integrity.get("valid", False),
                "verification_error": integrity.get("error"),
            }
        except Exception as exc:
            logger.error("Error getting stats: %s", exc)
            return {
                "total_events": 0,
                "total_students": 0,
                "last_event_timestamp": None,
                "hash_chain_verified": False,
                "verification_error": str(exc),
            }
