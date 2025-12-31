"""Pydantic schemas for appointments."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.appointment import AppointmentStatus, SyncStatus


class CustomerInfo(BaseModel):
    """Customer information in appointment response."""

    id: int
    email: str | None
    phone: str | None
    name: str | None

    model_config = {"from_attributes": True}


class AppointmentCreate(BaseModel):
    """Schema for creating an appointment."""

    customer_email: str = Field(..., max_length=255)
    customer_name: str | None = Field(default=None, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=50)
    title: str = Field(default="Appointment", max_length=255)
    service_type: str = Field(..., max_length=100)
    start_time: datetime  # ISO format, timezone-aware
    duration_minutes: int = Field(default=60, ge=15, le=480)
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    """Schema for updating an appointment."""

    title: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: AppointmentStatus | None = None


class AppointmentResponse(BaseModel):
    """Schema for appointment response."""

    id: int
    business_id: int
    customer: CustomerInfo
    title: str
    service_type: str
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus
    notes: str | None
    external_uid: str | None
    sync_status: SyncStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppointmentListResponse(BaseModel):
    """Schema for listing appointments."""

    appointments: list[AppointmentResponse]
    total: int


class BookingResult(BaseModel):
    """Result of a booking operation."""

    success: bool
    message: str
    appointment: AppointmentResponse | None = None


class RescheduleResult(BaseModel):
    """Result of a reschedule operation."""

    success: bool
    message: str
    appointment: AppointmentResponse | None = None

