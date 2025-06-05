from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, DateTime, func
import shortuuid


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class TimestampedModel(Base):
    """An abstract base model that includes timestamp fields."""

    __abstract__ = (
        True  # This tells SQLAlchemy not to create a table for TimestampedModel
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def generate_short_uuid():
    """Generates a short, URL-safe UUID."""
    return shortuuid.uuid()
