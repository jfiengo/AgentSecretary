"""Pydantic schemas for availability."""

from datetime import date, time

from pydantic import BaseModel, Field, field_validator


class AvailabilityRuleCreate(BaseModel):
    """Schema for creating an availability rule."""

    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: time
    end_time: time

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: time, info) -> time:
        """Validate that end_time is after start_time."""
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class AvailabilityRuleResponse(BaseModel):
    """Schema for availability rule response."""

    id: int
    business_id: int
    day_of_week: int
    start_time: time
    end_time: time

    model_config = {"from_attributes": True}


class AvailableSlot(BaseModel):
    """A single available time slot."""

    start_time: str  # ISO format datetime
    end_time: str  # ISO format datetime
    duration_minutes: int


class AvailableSlotsResponse(BaseModel):
    """Response containing available slots for a date."""

    business_id: int
    date: date
    timezone: str
    slots: list[AvailableSlot]
    duration_minutes: int

