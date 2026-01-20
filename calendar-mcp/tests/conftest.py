"""
Pytest fixtures for Calendar MCP Server tests.

This module provides shared fixtures for all tests including:
- Test database setup with SQLite (in-memory for speed)
- FastAPI test client with dependency overrides
- Sample data fixtures for businesses, customers, and appointments
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.api.dependencies import get_db
from app.api.routes import appointments, availability, businesses, oauth
from app.models import (
    Appointment,
    AppointmentStatus,
    AvailabilityRule,
    BlockedTime,
    Business,
    CalendarConnection,
    Customer,
    SyncStatus,
)


# Use SQLite for tests (in-memory, fast, no external dependencies)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine with SQLite-specific settings
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Required for in-memory SQLite with multiple connections
)

# Test session factory
test_async_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def create_test_app() -> FastAPI:
    """
    Create a test FastAPI app without the production lifespan.
    
    This avoids the production app trying to connect to PostgreSQL
    during test startup.
    """
    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        # Test lifespan does nothing - we handle DB setup in fixtures
        yield
    
    test_app = FastAPI(
        title="Calendar MCP Server (Test)",
        lifespan=test_lifespan,
    )
    
    # Include the same routers as production
    test_app.include_router(businesses.router)
    test_app.include_router(availability.router)
    test_app.include_router(appointments.router)
    test_app.include_router(oauth.router)
    
    @test_app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    @test_app.get("/")
    async def root():
        return {
            "name": "Calendar MCP Server",
            "version": "1.0.0",
            "docs": "/docs",
        }
    
    return test_app


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create an event loop for the test session.
    
    This fixture ensures all async tests share the same event loop,
    which is required for pytest-asyncio to work correctly.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database for each test.
    
    This fixture:
    1. Creates all tables before the test
    2. Yields a database session for the test to use
    3. Rolls back any changes and drops tables after the test
    
    Using in-memory SQLite ensures tests are isolated and fast.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with test_async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client(test_db: AsyncSession) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with database dependency override.
    
    This fixture:
    1. Creates a test app (without production lifespan that connects to PostgreSQL)
    2. Overrides the database dependency with our test SQLite database
    3. Yields a test client for making HTTP requests
    """
    # Create fresh test app for each test
    test_app = create_test_app()
    
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db
    
    test_app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(test_app) as test_client:
        yield test_client
    
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_business(test_db: AsyncSession) -> Business:
    """
    Create a sample business for testing.
    
    Returns a business with:
    - Name: "Test Business"
    - Timezone: America/New_York
    - Default appointment duration: 60 minutes
    """
    business = Business(
        name="Test Business",
        timezone="America/New_York",
        default_appointment_duration=60,
    )
    test_db.add(business)
    await test_db.flush()
    await test_db.refresh(business)
    return business


@pytest_asyncio.fixture
async def sample_availability_rules(
    test_db: AsyncSession, sample_business: Business
) -> list[AvailabilityRule]:
    """
    Create sample availability rules for Monday-Friday 9am-5pm.
    
    This simulates typical business hours for testing availability
    calculations and appointment booking within valid hours.
    """
    rules = []
    for day in range(5):  # Monday (0) through Friday (4)
        rule = AvailabilityRule(
            business_id=sample_business.id,
            day_of_week=day,
            start_time=time(9, 0),  # 9:00 AM
            end_time=time(17, 0),   # 5:00 PM
        )
        test_db.add(rule)
        rules.append(rule)
    
    await test_db.flush()
    for rule in rules:
        await test_db.refresh(rule)
    return rules


@pytest_asyncio.fixture
async def sample_customer(test_db: AsyncSession) -> Customer:
    """
    Create a sample customer for testing.
    
    Returns a customer with:
    - Email: test@example.com
    - Name: Test Customer
    - Phone: 555-1234
    """
    customer = Customer(
        email="test@example.com",
        name="Test Customer",
        phone="555-1234",
    )
    test_db.add(customer)
    await test_db.flush()
    await test_db.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def sample_appointment(
    test_db: AsyncSession,
    sample_business: Business,
    sample_customer: Customer,
    sample_availability_rules: list[AvailabilityRule],
) -> Appointment:
    """
    Create a sample appointment for testing.
    
    Creates an appointment:
    - On the next Monday at 10:00 AM Eastern
    - Duration: 60 minutes
    - Service type: "test_service"
    - Status: CONFIRMED
    
    Depends on sample_availability_rules to ensure the appointment
    falls within valid business hours.
    """
    # Find next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    
    # Create appointment at 10 AM UTC (represents 10 AM in business timezone for simplicity)
    start_time = datetime.combine(next_monday, time(10, 0))
    end_time = start_time + timedelta(hours=1)
    
    appointment = Appointment(
        business_id=sample_business.id,
        customer_id=sample_customer.id,
        title="Test Appointment",
        service_type="test_service",
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.CONFIRMED,
        notes="Test appointment notes",
        external_uid="test-uid-123",
        sync_status=SyncStatus.PENDING,
    )
    test_db.add(appointment)
    await test_db.flush()
    await test_db.refresh(appointment)
    return appointment


@pytest_asyncio.fixture
async def sample_blocked_time(
    test_db: AsyncSession,
    sample_business: Business,
) -> BlockedTime:
    """
    Create a sample blocked time for testing.
    
    Creates a 2-hour blocked time on the next Tuesday at 2 PM,
    useful for testing that availability correctly excludes blocked periods.
    """
    # Find next Tuesday
    today = date.today()
    days_until_tuesday = (1 - today.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7
    next_tuesday = today + timedelta(days=days_until_tuesday)
    
    start_time = datetime.combine(next_tuesday, time(14, 0))  # 2 PM
    end_time = start_time + timedelta(hours=2)
    
    blocked = BlockedTime(
        business_id=sample_business.id,
        start_time=start_time,
        end_time=end_time,
        reason="Owner unavailable",
    )
    test_db.add(blocked)
    await test_db.flush()
    await test_db.refresh(blocked)
    return blocked


def get_next_weekday(weekday: int) -> date:
    """
    Helper function to get the next occurrence of a weekday.
    
    Args:
        weekday: 0=Monday, 1=Tuesday, ..., 6=Sunday
    
    Returns:
        The date of the next occurrence of that weekday
    """
    today = date.today()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


@pytest_asyncio.fixture
async def sample_calendar_connection(
    test_db: AsyncSession,
    sample_business: Business,
) -> CalendarConnection:
    """
    Create a sample Google Calendar connection for testing.
    
    Returns a CalendarConnection with:
    - Provider: google
    - Encrypted access and refresh tokens
    - Token expiry in the future
    """
    from app.utils.encryption import encrypt_token
    
    connection = CalendarConnection(
        business_id=sample_business.id,
        provider="google",
        access_token=encrypt_token("test-access-token"),
        refresh_token=encrypt_token("test-refresh-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        calendar_id="primary",
    )
    test_db.add(connection)
    await test_db.flush()
    await test_db.refresh(connection)
    return connection


@pytest_asyncio.fixture
async def expired_calendar_connection(
    test_db: AsyncSession,
    sample_business: Business,
) -> CalendarConnection:
    """
    Create an expired Google Calendar connection for testing.
    
    Returns a CalendarConnection with token_expires_at in the past.
    """
    from app.utils.encryption import encrypt_token
    
    connection = CalendarConnection(
        business_id=sample_business.id,
        provider="google",
        access_token=encrypt_token("expired-access-token"),
        refresh_token=encrypt_token("expired-refresh-token"),
        token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        calendar_id="primary",
    )
    test_db.add(connection)
    await test_db.flush()
    await test_db.refresh(connection)
    return connection

