# app/worker/celery_app.py
from celery import Celery
from app.core.config import settings
from app.core.logging_config import (
    setup_logging,
)  # Ensure logging is configured for worker
import logging

# It's important to call setup_logging() early in the worker process as well.
setup_logging()
logger = logging.getLogger(__name__)

# The first argument to Celery is the name of the current module.
# This is needed so that names can be generated automatically when tasks are defined in that module.
# The `broker` argument specifies the URL of the message broker to use (Redis in this case).
# The `backend` argument specifies the result backend to use (also Redis here).
celery_app = Celery(
    "knowledge_worker",  # A name for your Celery application
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],  # List of modules to import when the worker starts
)

# Optional Celery configuration, see the application user guide.
celery_app.conf.update(
    task_serializer="json",  # Default is pickle, json is safer
    result_serializer="json",
    accept_content=["json"],  # Specify the content types to accept
    timezone="UTC",  # It's good practice to use UTC
    enable_utc=True,
    # task_acks_late=True, # Acknowledge tasks after they complete/fail (requires careful handling of idempotency)
    # worker_prefetch_multiplier=1, # If tasks are long-running and you want one task per worker process at a time
    # task_track_started=True, # To get 'STARTED' state for tasks
    # broker_connection_retry_on_startup=True, # Retry connecting to broker on startup
)

# Example: Configure a default queue if not specified elsewhere
# celery_app.conf.task_default_queue = 'technical_qna'

# Example: Define task routing if you have multiple queues
# celery_app.conf.task_routes = {
#     'app.worker.tasks.process_question_task': {'queue': 'technical_qna'},
#     # 'app.worker.tasks.another_task': {'queue': 'another_queue'},
# }


# You can also load configuration from a Celery config module if you have one:
# celery_app.config_from_object('app.worker.celeryconfig') # If you create celeryconfig.py

logger.info(
    f"Celery app '{celery_app.main}' initialized with broker: {settings.CELERY_BROKER_URL} and backend: {settings.CELERY_RESULT_BACKEND}"
)
logger.info(f"Celery worker will import tasks from: {celery_app.conf.include}")

if __name__ == "__main__":
    # This allows running celery worker directly for development, e.g.:
    # python -m app.worker.celery_app worker -l INFO -Q technical_qna
    # However, the command in docker-compose.yml is usually preferred.
    logger.info("Starting Celery worker directly (for development).")
    argv = [
        "worker",
        "--loglevel=INFO",  # Or use settings.LOG_LEVEL.lower()
        "--queues=technical_qna",  # Ensure this matches your task routing or default queue
        # '--concurrency=1', # Example concurrency
    ]
    celery_app.worker_main(argv)
