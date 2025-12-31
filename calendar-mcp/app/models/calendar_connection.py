"""CalendarConnection model for OAuth tokens."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CalendarConnection(Base):
    """OAuth connection to an external calendar provider."""

    __tablename__ = "calendar_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    provider: Mapped[str] = mapped_column(String(50), default="google")
    access_token: Mapped[str] = mapped_column(Text)  # Encrypted
    refresh_token: Mapped[str] = mapped_column(Text)  # Encrypted
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="calendar_connections")  # noqa: F821

