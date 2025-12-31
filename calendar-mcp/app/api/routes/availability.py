"""Availability rules routes."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.models import AvailabilityRule, Business
from app.schemas.availability import (
    AvailabilityRuleCreate,
    AvailabilityRuleResponse,
    AvailableSlotsResponse,
)
from app.services.availability import AvailabilityService

router = APIRouter(tags=["availability"])


@router.post(
    "/businesses/{business_id}/availability-rules",
    response_model=AvailabilityRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_availability_rule(
    business_id: int,
    rule_in: AvailabilityRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> AvailabilityRule:
    """Create an availability rule for a business."""
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
    
    rule = AvailabilityRule(
        business_id=business_id,
        day_of_week=rule_in.day_of_week,
        start_time=rule_in.start_time,
        end_time=rule_in.end_time,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.get(
    "/businesses/{business_id}/availability-rules",
    response_model=list[AvailabilityRuleResponse],
)
async def list_availability_rules(
    business_id: int,
    day_of_week: int | None = Query(default=None, ge=0, le=6),
    db: AsyncSession = Depends(get_db),
) -> list[AvailabilityRule]:
    """List availability rules for a business."""
    query = select(AvailabilityRule).where(
        AvailabilityRule.business_id == business_id
    )
    
    if day_of_week is not None:
        query = query.where(AvailabilityRule.day_of_week == day_of_week)
    
    query = query.order_by(AvailabilityRule.day_of_week, AvailabilityRule.start_time)
    
    result = await db.execute(query)
    return list(result.scalars().all())


@router.delete(
    "/businesses/{business_id}/availability-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_availability_rule(
    business_id: int,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an availability rule."""
    result = await db.execute(
        select(AvailabilityRule).where(
            and_(
                AvailabilityRule.id == rule_id,
                AvailabilityRule.business_id == business_id,
            )
        )
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Availability rule with ID {rule_id} not found for business {business_id}",
        )
    
    await db.delete(rule)


@router.get(
    "/businesses/{business_id}/availability",
    response_model=AvailableSlotsResponse,
)
async def get_available_slots(
    business_id: int,
    target_date: date = Query(..., alias="date"),
    duration_minutes: int = Query(default=60, ge=15, le=480),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get available time slots for a business on a specific date."""
    service = AvailabilityService(db)
    result = await service.get_available_slots(
        business_id=business_id,
        target_date=target_date,
        duration_minutes=duration_minutes,
    )
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    
    return result

