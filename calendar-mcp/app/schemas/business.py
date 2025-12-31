"""Pydantic schemas for Business."""

from datetime import datetime

from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    """Schema for creating a business."""

    name: str = Field(..., min_length=1, max_length=255)
    timezone: str = Field(default="America/New_York", max_length=50)
    default_appointment_duration: int = Field(default=60, ge=15, le=480)


class BusinessUpdate(BaseModel):
    """Schema for updating a business."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, max_length=50)
    default_appointment_duration: int | None = Field(default=None, ge=15, le=480)


class BusinessResponse(BaseModel):
    """Schema for business response."""

    id: int
    name: str
    timezone: str
    default_appointment_duration: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

