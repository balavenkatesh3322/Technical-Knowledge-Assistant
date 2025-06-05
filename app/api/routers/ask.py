# app/api/routers/ask.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session
from app.api import schemas  # Renamed to avoid conflict
from app.models.job import Job, JobStatus
from app.worker.celery_app import celery_app  # To access task signature

# It's better to import the task directly if possible, or define a helper in celery_app
# from app.worker.tasks import process_question_task # Assuming this task is defined
from app.api.dependencies import get_db
from app.core.config import settings
import logging
import shortuuid  # For job IDs

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ask",
    tags=["Knowledge Assistant"],
)


# This is a placeholder for the actual Celery task.
# In a real setup, you'd import the task itself from app.worker.tasks
# For example: from app.worker.tasks import process_question_task
# Here, we use send_task which is more generic but requires knowing the task name.
def enqueue_processing_task(job_id: str, question: str):
    """Helper to enqueue the Celery task."""
    try:
        # Ensure the task name matches what's registered in Celery
        # The name is often 'app.worker.tasks.process_question_task'
        # Or the custom name if specified in @celery_app.task(name="custom_task_name")
        task_name = "app.worker.tasks.process_question_task"  # Adjust if your task name is different
        celery_app.send_task(task_name, args=[job_id, question], task_id=job_id)
        logger.info(
            f"Job {job_id} enqueued for processing question: '{question[:50]}...'",
            extra={"job_id": job_id},
        )
    except Exception as e:
        logger.error(
            f"Failed to enqueue job {job_id}: {e}",
            exc_info=True,
            extra={"job_id": job_id},
        )
        # This is a critical failure. The job entry in DB might need to be marked as FAILED immediately,
        # or a retry mechanism for enqueueing could be considered.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue the question for processing. Please try again later.",
        )


@router.post(
    "", response_model=schemas.JobCreateResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ask_question(
    request: schemas.AskRequest,
    db: Session = Depends(get_db),
    # background_tasks: BackgroundTasks # Not typically used with Celery for the main task
):
    """
    Accepts a technical question, queues it for asynchronous processing,
    and returns a job ID.
    """
    job_id = shortuuid.uuid()  # Generate a unique job ID
    logger.info(
        f"Received question for new job {job_id}: '{request.question[:50]}...'",
        extra={"job_id": job_id},
    )

    # 1. Create job entry in the database
    db_job = Job(id=job_id, question=request.question, status=JobStatus.PENDING)
    try:
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        logger.info(
            f"Job {job_id} created in database with status PENDING.",
            extra={"job_id": job_id},
        )
    except Exception as e:
        db.rollback()
        logger.error(
            f"Database error creating job {job_id}: {e}",
            exc_info=True,
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record the job. Please try again.",
        )

    # 2. Enqueue task for Celery worker
    # This should be robust. If enqueueing fails, the job is in DB but won't be processed.
    # Consider strategies for this (e.g., a separate monitoring process for orphaned jobs).
    enqueue_processing_task(job_id=db_job.id, question=db_job.question)

    return schemas.JobCreateResponse(job_id=db_job.id, status=db_job.status)


@router.get("/{job_id}", response_model=schemas.JobResultResponse)
async def get_job_status_and_result(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the status and result (if available) of a previously submitted job.
    """
    logger.debug(f"Fetching status for job {job_id}", extra={"job_id": job_id})

    db_job = db.query(Job).filter(Job.id == job_id).first()

    if not db_job:
        logger.warning(f"Job {job_id} not found in database.", extra={"job_id": job_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )

    logger.info(
        f"Job {job_id} found with status: {db_job.status}", extra={"job_id": job_id}
    )

    # Calculate processing time if job is completed or failed and has timestamps
    processing_time = None
    if db_job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
        if (
            db_job.created_at and db_job.updated_at
        ):  # updated_at reflects completion/failure time
            time_delta = db_job.updated_at - db_job.created_at
            processing_time = round(time_delta.total_seconds(), 2)

    return schemas.JobResultResponse(
        id=db_job.id,
        question=db_job.question,
        status=db_job.status,
        created_at=db_job.created_at,
        updated_at=db_job.updated_at,
        result_text=db_job.result_text,
        sources_metadata=db_job.sources_metadata,  # Assumes this is already in the desired format
        processing_time_seconds=processing_time,
    )
