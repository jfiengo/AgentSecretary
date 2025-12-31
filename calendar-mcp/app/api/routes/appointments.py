"""Appointment routes."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.models import Appointment, AppointmentStatus, Business
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    BookingResult,
    RescheduleResult,
)
from app.services.booking import BookingService

router = APIRouter(tags=["appointments"])


@router.post(
    "/businesses/{business_id}/appointments",
    response_model=BookingResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment(
    business_id: int,
    appointment_in: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Book a new appointment."""
    service = BookingService(db)
    result = await service.book_appointment(
        business_id=business_id,
        customer_email=appointment_in.customer_email,
        start_time=appointment_in.start_time,
        service_type=appointment_in.service_type,
        duration_minutes=appointment_in.duration_minutes,
        title=appointment_in.title,
        notes=appointment_in.notes,
        customer_name=appointment_in.customer_name,
        customer_phone=appointment_in.customer_phone,
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result["message"],
        )
    
    return result


@router.get(
    "/businesses/{business_id}/appointments",
    response_model=list[AppointmentResponse],
)
async def list_appointments(
    business_id: int,
    target_date: date | None = Query(default=None, alias="date"),
    include_cancelled: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[Appointment]:
    """List appointments for a business."""
    # Verify business exists
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    business = result.scalar_one_or_none()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {business_id} not found",
        )
    
    if target_date:
        # Use booking service for date-specific query
        service = BookingService(db)
        schedule = await service.get_daily_schedule(business_id, target_date.isoformat())
        
        if "error" in schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=schedule["error"],
            )
        
        # Filter out cancelled if needed
        appointments = []
        for appt_data in schedule["appointments"]:
            if include_cancelled or appt_data["status"] != "cancelled":
                # Fetch full appointment object
                result = await db.execute(
                    select(Appointment).where(Appointment.id == appt_data["id"])
                )
                appt = result.scalar_one_or_none()
                if appt:
                    await db.refresh(appt, ["customer"])
                    appointments.append(appt)
        
        return appointments
    
    # Get all appointments for business
    query = select(Appointment).where(Appointment.business_id == business_id)
    
    if not include_cancelled:
        query = query.where(Appointment.status != AppointmentStatus.CANCELLED)
    
    query = query.order_by(Appointment.start_time.desc())
    
    result = await db.execute(query)
    appointments = list(result.scalars().all())
    
    for appt in appointments:
        await db.refresh(appt, ["customer"])
    
    return appointments


@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentResponse,
)
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
) -> Appointment:
    """Get an appointment by ID."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found",
        )
    
    await db.refresh(appointment, ["customer"])
    return appointment


@router.patch(
    "/appointments/{appointment_id}",
    response_model=AppointmentResponse,
)
async def update_appointment(
    appointment_id: int,
    appointment_in: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> Appointment:
    """Update an appointment."""
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found",
        )
    
    update_data = appointment_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(appointment, field, value)
    
    await db.flush()
    await db.refresh(appointment, ["customer"])
    return appointment


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=BookingResult,
)
async def cancel_appointment(
    appointment_id: int,
    reason: str = "",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel an appointment."""
    service = BookingService(db)
    result = await service.cancel_appointment(appointment_id, reason)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"],
        )
    
    return result


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=RescheduleResult,
)
async def reschedule_appointment(
    appointment_id: int,
    new_start_time: str = Query(..., description="New start time in ISO format"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reschedule an appointment."""
    from datetime import datetime
    
    try:
        parsed_time = datetime.fromisoformat(new_start_time)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid new_start_time format. Use ISO format.",
        )
    
    service = BookingService(db)
    result = await service.reschedule_appointment(appointment_id, parsed_time)
    
    if not result["success"]:
        status_code = status.HTTP_404_NOT_FOUND
        if "conflict" in result["message"].lower():
            status_code = status.HTTP_409_CONFLICT
        
        raise HTTPException(
            status_code=status_code,
            detail=result["message"],
        )
    
    return result

