"""Business and AvailabilityRule models."""

from datetime import datetime, time

from sqlalchemy import ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Business(Base):
    """A business that can receive appointments."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    default_appointment_duration: Mapped[int] = mapped_column(default=60)  # minutes
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    availability_rules: Mapped[list["AvailabilityRule"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    appointments: Mapped[list["Appointment"]] = relationship(  # noqa: F821
        back_populates="business", cascade="all, delete-orphan"
    )
    blocked_times: Mapped[list["BlockedTime"]] = relationship(  # noqa: F821
        back_populates="business", cascade="all, delete-orphan"
    )
    calendar_connections: Mapped[list["CalendarConnection"]] = relationship(  # noqa: F821
        back_populates="business", cascade="all, delete-orphan"
    )


class AvailabilityRule(Base):
    """Business hours for a specific day of the week."""

    __tablename__ = "availability_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    day_of_week: Mapped[int] = mapped_column()  # 0=Monday, 6=Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="availability_rules")

