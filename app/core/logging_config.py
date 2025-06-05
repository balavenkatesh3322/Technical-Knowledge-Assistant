# app/core/logging_config.py
import logging
import sys
from pythonjsonlogger import jsonlogger
from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get("timestamp"):
            log_record["timestamp"] = record.created
        if log_record.get("level"):
            log_record["level"] = log_record["level"].upper()
        else:
            log_record["level"] = record.levelname

        # Add context from record if available (e.g., job_id)
        if hasattr(record, "job_id") and record.job_id is not None:
            log_record["job_id"] = record.job_id


def setup_logging():
    log_level = settings.LOG_LEVEL.upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicate logs if this function is called multiple times
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler with JSON Formatter
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s %(job_id)s"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configure specific loggers if needed (e.g., for libraries)
    logging.getLogger("uvicorn.access").setLevel(
        logging.WARNING
    )  # Quieten access logs unless error
    logging.getLogger("uvicorn.error").setLevel(numeric_level)
    logging.getLogger("celery").setLevel(numeric_level)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING
    )  # Set to INFO for query logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb.telemetry.posthog").setLevel(
        logging.WARNING
    )  # Silence ChromaDB telemetry logs

    # Test log
    # logging.info("Logging configured with level %s", log_level, extra={"job_id": "system_init"})


# Call setup_logging() when this module is imported,
# or call it explicitly in your main application entry points (FastAPI main, Celery app).
# For simplicity here, we might call it in main.py and celery_app.py.
