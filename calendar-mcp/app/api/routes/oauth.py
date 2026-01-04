"""Google OAuth flow routes."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.config import get_settings
from app.models import Business, CalendarConnection
from app.utils.encryption import decrypt_token, encrypt_token

router = APIRouter(prefix="/oauth", tags=["oauth"])

settings = get_settings()

# Google OAuth scopes for calendar access
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_oauth_flow() -> Flow:
    """Create Google OAuth flow instance."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    
    return flow


@router.get("/google/authorize")
async def google_authorize(
    business_id: int = Query(..., description="Business ID to connect calendar for"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Start Google OAuth flow.
    
    Redirects the user to Google's consent page.
    """
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
    
    flow = get_oauth_flow()
    
    # Generate authorization URL with state containing business_id
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(business_id),
    )
    
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter containing business_id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Handle Google OAuth callback.
    
    Exchanges the authorization code for tokens and stores them.
    """
    # Parse business_id from state
    try:
        business_id = int(state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )
    
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
    
    # Exchange code for tokens
    flow = get_oauth_flow()
    
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange authorization code: {str(e)}",
        )
    
    credentials = flow.credentials
    
    # Calculate token expiry
    token_expires_at = datetime.utcnow() + timedelta(seconds=3600)
    if credentials.expiry:
        token_expires_at = credentials.expiry
    
    # Check for existing connection
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.business_id == business_id,
            CalendarConnection.provider == "google",
        )
    )
    connection = result.scalar_one_or_none()
    
    if connection:
        # Update existing connection
        connection.access_token = encrypt_token(credentials.token)
        connection.refresh_token = encrypt_token(credentials.refresh_token or "")
        connection.token_expires_at = token_expires_at
    else:
        # Create new connection
        connection = CalendarConnection(
            business_id=business_id,
            provider="google",
            access_token=encrypt_token(credentials.token),
            refresh_token=encrypt_token(credentials.refresh_token or ""),
            token_expires_at=token_expires_at,
            calendar_id="primary",  # Default to primary calendar
        )
        db.add(connection)
    
    await db.flush()
    
    return {
        "success": True,
        "message": "Google Calendar connected successfully",
        "business_id": business_id,
    }


@router.get("/google/status/{business_id}")
async def google_connection_status(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check if a business has a Google Calendar connection."""
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.business_id == business_id,
            CalendarConnection.provider == "google",
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        return {
            "connected": False,
            "business_id": business_id,
        }
    
    # Check if token is expired
    is_expired = connection.token_expires_at < datetime.utcnow()
    
    return {
        "connected": True,
        "business_id": business_id,
        "calendar_id": connection.calendar_id,
        "token_expired": is_expired,
    }


@router.delete("/google/disconnect/{business_id}")
async def disconnect_google(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disconnect Google Calendar from a business."""
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.business_id == business_id,
            CalendarConnection.provider == "google",
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Google Calendar connection found for business {business_id}",
        )
    
    await db.delete(connection)
    
    return {
        "success": True,
        "message": "Google Calendar disconnected successfully",
        "business_id": business_id,
    }


@router.post("/google/sync/{business_id}")
async def sync_to_google_calendar(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Manually sync all pending appointments to Google Calendar.
    
    This pushes any appointments with sync_status='pending' to Google Calendar.
    """
    from app.services.google_calendar import GoogleCalendarService
    
    # Check connection exists
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.business_id == business_id,
            CalendarConnection.provider == "google",
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Google Calendar connection found for business {business_id}",
        )
    
    service = GoogleCalendarService(db)
    result = await service.sync_pending_appointments(business_id)
    
    return result


async def get_google_credentials(
    business_id: int,
    db: AsyncSession,
) -> Credentials | None:
    """
    Get Google credentials for a business.
    
    Handles token refresh if needed.
    """
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.business_id == business_id,
            CalendarConnection.provider == "google",
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        return None
    
    # Decrypt tokens
    access_token = decrypt_token(connection.access_token)
    refresh_token = decrypt_token(connection.refresh_token) if connection.refresh_token else None
    
    # Ensure expiry is timezone-naive (Google's library expects naive UTC)
    token_expiry = connection.token_expires_at
    if token_expiry and token_expiry.tzinfo is not None:
        token_expiry = token_expiry.replace(tzinfo=None)
    
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        expiry=token_expiry,
    )
    
    # Refresh if expired
    if credentials.expired and credentials.refresh_token:
        try:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            
            # Update stored tokens
            connection.access_token = encrypt_token(credentials.token)
            connection.token_expires_at = credentials.expiry or datetime.utcnow() + timedelta(hours=1)
            await db.flush()
        except Exception:
            # Token refresh failed
            return None
    
    return credentials

