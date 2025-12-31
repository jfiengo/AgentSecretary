"""Business CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.models import Business
from app.schemas.business import BusinessCreate, BusinessResponse, BusinessUpdate

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def create_business(
    business_in: BusinessCreate,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Create a new business."""
    business = Business(
        name=business_in.name,
        timezone=business_in.timezone,
        default_appointment_duration=business_in.default_appointment_duration,
    )
    db.add(business)
    await db.flush()
    await db.refresh(business)
    return business


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Get a business by ID."""
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    business = result.scalar_one_or_none()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {business_id} not found",
        )
    
    return business


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: int,
    business_in: BusinessUpdate,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Update a business."""
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    business = result.scalar_one_or_none()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {business_id} not found",
        )
    
    update_data = business_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)
    
    await db.flush()
    await db.refresh(business)
    return business


@router.delete("/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a business."""
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    business = result.scalar_one_or_none()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with ID {business_id} not found",
        )
    
    await db.delete(business)


@router.get("", response_model=list[BusinessResponse])
async def list_businesses(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> list[Business]:
    """List all businesses."""
    result = await db.execute(
        select(Business).offset(skip).limit(limit)
    )
    return list(result.scalars().all())

