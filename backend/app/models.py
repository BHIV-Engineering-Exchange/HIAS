from sqlalchemy import Column, String, Integer, DateTime, Boolean, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from .schemas import Direction, Method, Decision, Reason

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, default="Resident")
    ref_user_id = Column(Integer, unique=True, index=True, nullable=True)
    department = Column(String, default="Hostel Resident")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credentials = relationship("Credential", back_populates="user", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="user")


class Credential(Base):
    __tablename__ = "credentials"

    credential_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    type = Column(String, nullable=False)  # RFID, FACE, PIN
    card_number = Column(String, unique=True, index=True, nullable=True) # 64-bit CSN / card number
    face_data = Column(Text, nullable=True)  # JPEG template / base64
    status = Column(String, default="SYNCED")  # PENDING, SYNCED, REVOKED, FAILED
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="credentials")
    sync_records = relationship("GateSyncStatus", back_populates="credential", cascade="all, delete-orphan")


class Gate(Base):
    __tablename__ = "gates"

    gate_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, default="Hostel Campus")
    direction = Column(String, default="IN")  # IN, OUT
    device_ip = Column(String, default="192.168.1.100")
    device_port = Column(Integer, default=80)
    device_model = Column(String, default="COSEC ARGO FACE")
    device_type = Column(String, default="COSEC")  # COSEC, RELAY_GPIO, MOCK
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)

    sync_records = relationship("GateSyncStatus", back_populates="gate", cascade="all, delete-orphan")


class GateSyncStatus(Base):
    __tablename__ = "gate_sync_status"

    id = Column(String, primary_key=True, index=True)
    credential_id = Column(String, ForeignKey("credentials.credential_id"), nullable=False, index=True)
    gate_id = Column(String, ForeignKey("gates.gate_id"), nullable=False, index=True)
    status = Column(String, default="SYNCED")  # PENDING, SYNCED, RETRYING, FAILED
    retry_count = Column(Integer, default=0)
    last_error = Column(String, nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    credential = relationship("Credential", back_populates="sync_records")
    gate = relationship("Gate", back_populates="sync_records")


class Event(Base):
    __tablename__ = "events"
    
    trace_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True, nullable=True)
    name = Column(String)
    direction = Column(SQLEnum(Direction), nullable=True)
    method = Column(SQLEnum(Method), nullable=True)
    decision = Column(SQLEnum(Decision), nullable=True)
    reason = Column(String, nullable=True)
    device_id = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="events")


class Setting(Base):
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String) # We'll store as JSON string or individual keys
