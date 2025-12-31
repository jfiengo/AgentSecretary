"""Availability calculation service."""

from datetime import date, datetime, time, timedelta

import pytz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, AvailabilityRule, BlockedTime, Business


class AvailabilityService:
    """Service for calculating available appointment slots."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_business(self, business_id: int) -> Business | None:
        """Get a business by ID."""
        result = await self.db.execute(
            select(Business).where(Business.id == business_id)
        )
        return result.scalar_one_or_none()

    async def get_availability_rules(
        self, business_id: int, day_of_week: int
    ) -> list[AvailabilityRule]:
        """Get availability rules for a business on a specific day."""
        result = await self.db.execute(
            select(AvailabilityRule).where(
                and_(
                    AvailabilityRule.business_id == business_id,
                    AvailabilityRule.day_of_week == day_of_week,
                )
            )
        )
        return list(result.scalars().all())

    async def get_appointments_for_date(
        self, business_id: int, target_date: date, timezone: str
    ) -> list[Appointment]:
        """Get all confirmed appointments for a business on a specific date."""
        tz = pytz.timezone(timezone)
        
        # Create datetime range for the target date in business timezone
        start_of_day = tz.localize(datetime.combine(target_date, time.min))
        end_of_day = tz.localize(datetime.combine(target_date, time.max))
        
        # Convert to UTC for database query
        start_utc = start_of_day.astimezone(pytz.UTC)
        end_utc = end_of_day.astimezone(pytz.UTC)

        result = await self.db.execute(
            select(Appointment).where(
                and_(
                    Appointment.business_id == business_id,
                    Appointment.status == AppointmentStatus.CONFIRMED,
                    Appointment.start_time >= start_utc,
                    Appointment.start_time <= end_utc,
                )
            )
        )
        return list(result.scalars().all())

    async def get_blocked_times_for_date(
        self, business_id: int, target_date: date, timezone: str
    ) -> list[BlockedTime]:
        """Get all blocked times for a business on a specific date."""
        tz = pytz.timezone(timezone)
        
        start_of_day = tz.localize(datetime.combine(target_date, time.min))
        end_of_day = tz.localize(datetime.combine(target_date, time.max))
        
        start_utc = start_of_day.astimezone(pytz.UTC)
        end_utc = end_of_day.astimezone(pytz.UTC)

        result = await self.db.execute(
            select(BlockedTime).where(
                and_(
                    BlockedTime.business_id == business_id,
                    BlockedTime.start_time < end_utc,
                    BlockedTime.end_time > start_utc,
                )
            )
        )
        return list(result.scalars().all())

    async def get_available_slots(
        self,
        business_id: int,
        target_date: date,
        duration_minutes: int = 60,
    ) -> dict:
        """
        Calculate available time slots for a given date.
        
        Returns a dict with:
        - business_id: int
        - date: str (YYYY-MM-DD)
        - timezone: str
        - duration_minutes: int
        - slots: list of {start_time, end_time, duration_minutes}
        """
        business = await self.get_business(business_id)
        if not business:
            return {
                "business_id": business_id,
                "date": target_date.isoformat(),
                "timezone": "UTC",
                "duration_minutes": duration_minutes,
                "slots": [],
                "error": "Business not found",
            }

        timezone = business.timezone
        tz = pytz.timezone(timezone)
        
        # Get day of week (Python: Monday=0, Sunday=6)
        day_of_week = target_date.weekday()
        
        # Get availability rules for this day
        rules = await self.get_availability_rules(business_id, day_of_week)
        if not rules:
            return {
                "business_id": business_id,
                "date": target_date.isoformat(),
                "timezone": timezone,
                "duration_minutes": duration_minutes,
                "slots": [],
            }

        # Get existing appointments and blocked times
        appointments = await self.get_appointments_for_date(
            business_id, target_date, timezone
        )
        blocked_times = await self.get_blocked_times_for_date(
            business_id, target_date, timezone
        )

        # Generate all possible slots from availability rules
        all_slots = []
        for rule in rules:
            slots = self._generate_slots_from_rule(
                target_date, rule, duration_minutes, tz
            )
            all_slots.extend(slots)

        # Remove slots that conflict with appointments or blocked times
        available_slots = []
        for slot_start, slot_end in all_slots:
            if not self._has_conflict(
                slot_start, slot_end, appointments, blocked_times
            ):
                available_slots.append({
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat(),
                    "duration_minutes": duration_minutes,
                })

        return {
            "business_id": business_id,
            "date": target_date.isoformat(),
            "timezone": timezone,
            "duration_minutes": duration_minutes,
            "slots": available_slots,
        }

    def _generate_slots_from_rule(
        self,
        target_date: date,
        rule: AvailabilityRule,
        duration_minutes: int,
        tz: pytz.BaseTzInfo,
    ) -> list[tuple[datetime, datetime]]:
        """Generate time slots from an availability rule."""
        slots = []
        
        # Create start and end datetime in business timezone
        rule_start = tz.localize(datetime.combine(target_date, rule.start_time))
        rule_end = tz.localize(datetime.combine(target_date, rule.end_time))
        
        duration = timedelta(minutes=duration_minutes)
        current = rule_start
        
        while current + duration <= rule_end:
            slot_end = current + duration
            slots.append((current, slot_end))
            current = slot_end  # Non-overlapping slots
        
        return slots

    def _has_conflict(
        self,
        slot_start: datetime,
        slot_end: datetime,
        appointments: list[Appointment],
        blocked_times: list[BlockedTime],
    ) -> bool:
        """Check if a slot conflicts with any appointments or blocked times."""
        # Convert slot times to UTC for comparison
        slot_start_utc = slot_start.astimezone(pytz.UTC)
        slot_end_utc = slot_end.astimezone(pytz.UTC)
        
        # Check appointments
        for appt in appointments:
            appt_start = appt.start_time
            appt_end = appt.end_time
            
            # Ensure timezone awareness
            if appt_start.tzinfo is None:
                appt_start = pytz.UTC.localize(appt_start)
            if appt_end.tzinfo is None:
                appt_end = pytz.UTC.localize(appt_end)
            
            # Check for overlap
            if slot_start_utc < appt_end and slot_end_utc > appt_start:
                return True
        
        # Check blocked times
        for block in blocked_times:
            block_start = block.start_time
            block_end = block.end_time
            
            if block_start.tzinfo is None:
                block_start = pytz.UTC.localize(block_start)
            if block_end.tzinfo is None:
                block_end = pytz.UTC.localize(block_end)
            
            if slot_start_utc < block_end and slot_end_utc > block_start:
                return True
        
        return False

    async def is_slot_available(
        self,
        business_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if a specific time slot is available."""
        business = await self.get_business(business_id)
        if not business:
            return False

        timezone = business.timezone
        tz = pytz.timezone(timezone)
        
        # Ensure times are timezone-aware
        if start_time.tzinfo is None:
            start_time = pytz.UTC.localize(start_time)
        if end_time.tzinfo is None:
            end_time = pytz.UTC.localize(end_time)
        
        # Convert to business timezone to get the date
        start_local = start_time.astimezone(tz)
        target_date = start_local.date()
        
        # Check if within business hours
        day_of_week = target_date.weekday()
        rules = await self.get_availability_rules(business_id, day_of_week)
        
        within_hours = False
        for rule in rules:
            rule_start = tz.localize(datetime.combine(target_date, rule.start_time))
            rule_end = tz.localize(datetime.combine(target_date, rule.end_time))
            
            if start_local >= rule_start and start_local.astimezone(tz).time() < rule.end_time:
                end_local = end_time.astimezone(tz)
                if end_local <= rule_end:
                    within_hours = True
                    break
        
        if not within_hours:
            return False
        
        # Check for conflicts
        appointments = await self.get_appointments_for_date(
            business_id, target_date, timezone
        )
        blocked_times = await self.get_blocked_times_for_date(
            business_id, target_date, timezone
        )
        
        return not self._has_conflict(start_time, end_time, appointments, blocked_times)

