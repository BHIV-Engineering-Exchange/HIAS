"""Configuration for the MongoDB-backed storage service."""

from __future__ import annotations

import os
from typing import Optional


def load_env_file() -> None:
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_file):
        return

    with open(env_file, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()


try:
    load_env_file()
except Exception as exc:
    print(f"Warning: Could not load .env file: {exc}")


class Settings:
    SERVICE_NAME: str = "storage-service"
    SERVICE_PORT: int = int(os.getenv("STORAGE_SERVICE_PORT", 8005))
    SERVICE_HOST: str = os.getenv("STORAGE_SERVICE_HOST", "0.0.0.0")
    SERVICE_ENV: str = os.getenv("SERVICE_ENV", "development")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "mongodb+srv://localhost")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "hias")
    MONGODB_EVENTS_COLLECTION: str = os.getenv("MONGODB_EVENTS_COLLECTION", "events")
    MONGODB_CHAIN_STATE_COLLECTION: str = os.getenv("MONGODB_CHAIN_STATE_COLLECTION", "chain_state")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SCHEMA_DIR: str = os.getenv("SCHEMA_DIR", "./shared-contracts/schemas")
    STRICT_SCHEMA_VALIDATION: bool = os.getenv("STRICT_SCHEMA_VALIDATION", "true").lower() == "true"

    SYSTEM_ID: str = "HIAS"
    OBSERVABILITY_SERVICE_URL: Optional[str] = os.getenv("OBSERVABILITY_SERVICE_URL", None)
    EMIT_OBSERVABILITY_SIGNALS: bool = os.getenv("EMIT_OBSERVABILITY_SIGNALS", "true").lower() == "true"

    HASH_CHAIN_VERIFICATION_ENABLED: bool = os.getenv("HASH_CHAIN_VERIFICATION_ENABLED", "true").lower() == "true"
    VERIFY_CHAIN_ON_READ: bool = os.getenv("VERIFY_CHAIN_ON_READ", "false").lower() == "true"

    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", 100))
    CONNECTION_TIMEOUT: int = int(os.getenv("CONNECTION_TIMEOUT", 30))

    ENABLE_STATS_ENDPOINT: bool = os.getenv("ENABLE_STATS_ENDPOINT", "true").lower() == "true"
    ENABLE_HEALTH_CHECK: bool = os.getenv("ENABLE_HEALTH_CHECK", "true").lower() == "true"

    API_VERSION: str = "v1"
    API_TITLE: str = "HIAS Storage Service"
    API_DESCRIPTION: str = "Append-only, hash-linked immutable event storage"

    def __repr__(self) -> str:
        return (
            "Storage Service Configuration:\n"
            f"  Service: {self.SERVICE_NAME} ({self.SERVICE_ENV})\n"
            f"  Host: {self.SERVICE_HOST}:{self.SERVICE_PORT}\n"
            f"  Database: {self.DATABASE_URL}\n"
            f"  Mongo DB: {self.MONGODB_DB_NAME}\n"
            f"  Schema Validation: {'Strict' if self.STRICT_SCHEMA_VALIDATION else 'Lenient'}\n"
            f"  Hash Chain Verification: {self.HASH_CHAIN_VERIFICATION_ENABLED}\n"
            f"  Observability: {self.EMIT_OBSERVABILITY_SIGNALS}"
        )


settings = Settings()
