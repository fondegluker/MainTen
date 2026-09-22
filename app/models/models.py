import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    TECHNICIAN = "TECHNICIAN"
    USER = "USER"
    OBSERVER = "OBSERVER"


class MaintenanceEventStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    MISSED = "missed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email_or_login: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="ru", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    computers: Mapped[list["Computer"]] = relationship("Computer", back_populates="owner_user", foreign_keys="[Computer.owner_user_id]")
    assigned_events: Mapped[list["MaintenanceEvent"]] = relationship("MaintenanceEvent", back_populates="technician")


class Computer(Base):
    __tablename__ = "computers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hostname: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    mac: Mapped[str | None] = mapped_column(String(17), nullable=True)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    is_round_the_clock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_maintenance_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_maintenance_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner_user: Mapped[Optional["User"]] = relationship("User", back_populates="computers")
    maintenance_events: Mapped[list["MaintenanceEvent"]] = relationship("MaintenanceEvent", back_populates="computer")


class MaintenanceProtocolItem(Base):
    __tablename__ = "maintenance_protocol_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(Integer, ForeignKey("computers.id"), nullable=False)
    technician_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    scheduled_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    scheduled_slot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[MaintenanceEventStatus] = mapped_column(
        Enum(MaintenanceEventStatus), default=MaintenanceEventStatus.PLANNED, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    computer: Mapped["Computer"] = relationship("Computer", back_populates="maintenance_events")
    technician: Mapped[Optional["User"]] = relationship("User", back_populates="assigned_events")
    checks: Mapped[list["MaintenanceEventCheck"]] = relationship("MaintenanceEventCheck", back_populates="event", cascade="all, delete-orphan")
    attachments: Mapped[list["MaintenanceEventAttachment"]] = relationship("MaintenanceEventAttachment", back_populates="event", cascade="all, delete-orphan")


class MaintenanceEventCheck(Base):
    __tablename__ = "maintenance_event_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("maintenance_events.id"), nullable=False)
    protocol_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("maintenance_protocol_items.id"), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped["MaintenanceEvent"] = relationship("MaintenanceEvent", back_populates="checks")
    protocol_item: Mapped["MaintenanceProtocolItem"] = relationship("MaintenanceProtocolItem")


class MaintenanceEventAttachment(Base):
    __tablename__ = "maintenance_event_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("maintenance_events.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    event: Mapped["MaintenanceEvent"] = relationship("MaintenanceEvent", back_populates="attachments")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    computer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("computers.id"), nullable=True)
    event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("maintenance_events.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), default="windows_agent", nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON, nullable=False)
