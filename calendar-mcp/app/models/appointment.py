"""Appointment and BlockedTime models."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AppointmentStatus(enum.Enum):
    """Status of an appointment."""

    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class SyncStatus(enum.Enum):
    """Sync status with external calendar."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class Appointment(Base):
    """An appointment booked by a customer."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    title: Mapped[str] = mapped_column(String(255))
    service_type: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.CONFIRMED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), default=SyncStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="appointments")  # noqa: F821
    customer: Mapped["Customer"] = relationship(back_populates="appointments")  # noqa: F821


class BlockedTime(Base):
    """A blocked time period when appointments cannot be scheduled."""

    __tablename__ = "blocked_times"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="blocked_times")  # noqa: F821

