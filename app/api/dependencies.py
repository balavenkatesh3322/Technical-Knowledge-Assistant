# app/api/dependencies.py
from typing import Generator
from sqlalchemy.orm import Session as SQLAlchemySession
from app.db.session import (
    SessionLocal,
    engine as db_engine,
)  # import engine for health check
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


def get_db() -> Generator[SQLAlchemySession, None, None]:
    if SessionLocal is None:
        logger.error(
            "Database session (SessionLocal) is not initialized. Cannot get DB session."
        )
        # This should ideally not happen if session.py initializes correctly.
        # Raising a 503 Service Unavailable might be more appropriate.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available.",
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Example of a database health check dependency
async def get_db_health() -> bool:
    if db_engine is None:
        logger.error("Database engine is not initialized.")
        return False
    try:
        with db_engine.connect() as connection:
            # You can execute a simple query like "SELECT 1"
            # connection.execute(text("SELECT 1"))
            return True  # If connect() doesn't raise an exception, connection is likely okay
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return False


# Placeholder for rate limiting dependency using slowapi if you implement it
# from slowapi import Limiter
# from slowapi.util import get_remote_address
# from app.core.config import settings

# limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_TIMES}/minute"])
