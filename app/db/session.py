# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

try:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine and session created successfully.")
    # You could try a test connection here if needed
    # with engine.connect() as connection:
    #     logger.info("Successfully connected to the database.")
except Exception as e:
    logger.error(f"Failed to create database engine or session: {e}", exc_info=True)
    # Fallback or raise critical error if DB is essential at startup
    engine = None
    SessionLocal = None


# Dependency for FastAPI
def get_db() -> SQLAlchemySession:
    if SessionLocal is None:
        logger.error(
            "Database session (SessionLocal) is not initialized. Cannot get DB session."
        )
        raise RuntimeError("Database session not initialized.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
