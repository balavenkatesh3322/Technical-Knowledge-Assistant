# app/worker/tasks.py
from typing import Optional
from app.worker.celery_app import celery_app
from app.core.config import settings
from app.core.logging_config import setup_logging  # Ensure logging is configured
from app.db.session import SessionLocal  # For creating DB sessions within tasks
from app.models.job import Job, JobStatus
from app.services.vector_db_client import get_vector_db_client, VectorDBClient
from app.services.llm_client import get_llm_client, LLMClient
from app.worker.logic.retrieval import HybridRetriever
from app.worker.logic.generation import AnswerGenerator
import logging
import time
import datetime
from sqlalchemy.orm import Session as SQLAlchemySession

# It's good practice to ensure logging is set up when the module is loaded by Celery
setup_logging()
logger = logging.getLogger(__name__)


def update_job_in_db(
    db: SQLAlchemySession,
    job_id: str,
    status: JobStatus,
    result_text: Optional[str] = None,
    sources_metadata: Optional[list[dict]] = None,
):
    """Helper function to update job status and result in the database."""
    try:
        db_job = db.query(Job).filter(Job.id == job_id).first()
        if db_job:
            db_job.status = status
            if result_text is not None:
                db_job.result_text = result_text
            if sources_metadata is not None:
                db_job.sources_metadata = (
                    sources_metadata  # Ensure this is JSON serializable
                )
            db_job.updated_at = datetime.datetime.utcnow()  # Explicitly set for clarity
            db.commit()
            logger.info(
                f"Job {job_id} status updated to {status}.", extra={"job_id": job_id}
            )
        else:
            logger.error(
                f"Job {job_id} not found in database for update.",
                extra={"job_id": job_id},
            )
    except Exception as e:
        db.rollback()
        logger.error(
            f"Database error updating job {job_id}: {e}",
            exc_info=True,
            extra={"job_id": job_id},
        )
        # Depending on the error, you might want to re-raise or handle differently


@celery_app.task(
    bind=True,  # Makes `self` (the task instance) available
    name="app.worker.tasks.process_question_task",  # Explicit name is good practice
    acks_late=True,  # Acknowledge after task completion/failure
    max_retries=3,  # Example: retry up to 3 times
    default_retry_delay=60,  # Example: wait 60 seconds before retrying
)
def process_question_task(self, job_id: str, question: str):
    """
    Celery task to process a technical question:
    1. Update job status to PROCESSING.
    2. Perform hybrid retrieval.
    3. Generate answer using LLM.
    4. Update job status to COMPLETED with result, or FAILED.
    """
    # Create a logger adapter to include job_id in all log messages from this task
    task_logger = logging.LoggerAdapter(logger, {"job_id": job_id})
    task_logger.info(f"Task started for question: '{question[:50]}...'")

    db: SQLAlchemySession = SessionLocal()  # Create a new DB session for this task

    try:
        # 1. Update job status to PROCESSING
        update_job_in_db(db, job_id, JobStatus.PROCESSING)
        task_logger.info("Job status updated to PROCESSING.")

        # Initialize services (this can raise exceptions if services are unavailable)
        # These `get_` functions will initialize the clients if they haven't been already.
        # In a long-running worker, these might be initialized once per worker process.
        # However, for robustness against transient issues, initializing per task (or with retry) can be safer.
        try:
            vector_db_client: VectorDBClient = get_vector_db_client()
            llm_client: LLMClient = get_llm_client()
        except ConnectionError as conn_err:
            task_logger.error(
                f"Failed to connect to dependent services: {conn_err}", exc_info=True
            )
            update_job_in_db(
                db,
                job_id,
                JobStatus.FAILED,
                result_text=f"Service connection error: {conn_err}",
            )
            # self.retry(exc=conn_err) # This will use Celery's retry mechanism
            # For now, just fail the task if critical services are down.
            # Or, if you want Celery to retry, raise the exception that `autoretry_for` would catch.
            raise  # Re-raise to let Celery handle retries based on task config
        except Exception as service_init_err:  # Catch any other init errors
            task_logger.error(
                f"Unexpected error initializing services: {service_init_err}",
                exc_info=True,
            )
            update_job_in_db(
                db,
                job_id,
                JobStatus.FAILED,
                result_text=f"Service initialization error: {service_init_err}",
            )
            raise

        retriever = HybridRetriever(
            vector_db_client=vector_db_client, top_k=settings.RETRIEVAL_TOP_K
        )
        answer_generator = AnswerGenerator(llm_client=llm_client)

        # 2. Perform hybrid retrieval
        task_logger.info(
            f"Starting passage retrieval for question: '{question[:50]}...'"
        )
        start_time_retrieval = time.time()
        retrieved_passages = retriever.retrieve_passages(question)  # List of dicts
        retrieval_duration = time.time() - start_time_retrieval
        task_logger.info(
            f"Passage retrieval completed in {retrieval_duration:.2f}s. Found {len(retrieved_passages)} passages."
        )

        if not retrieved_passages:
            task_logger.warning(
                "No passages retrieved. Proceeding to generate answer without specific context."
            )
            # An alternative here could be to fail the job or return a specific message.

        # 3. Generate answer using LLM
        task_logger.info("Starting answer generation...")
        start_time_generation = time.time()
        generated_answer = answer_generator.generate_answer(
            question, retrieved_passages
        )
        generation_duration = time.time() - start_time_generation
        task_logger.info(f"Answer generation completed in {generation_duration:.2f}s.")

        if generated_answer is None:
            task_logger.error("Answer generation failed or returned None.")
            # This could be a retryable error depending on the cause.
            update_job_in_db(
                db,
                job_id,
                JobStatus.FAILED,
                result_text="Failed to generate an answer.",
            )
            # Consider if this should be retried by Celery
            raise Exception(
                "LLM answer generation returned None"
            )  # To trigger potential retry

        # Prepare sources metadata for DB storage from retrieved_passages
        # The 'retrieved_passages' are dicts: {'chunk_id', 'text', 'score', 'source_id', 'url'}
        sources_for_db = [
            {
                "source_id": p.get("source_id"),
                "chunk_id": p.get("chunk_id"),
                "relevance_score": p.get("score"),
                "url": p.get("url"),
                # "retrieved_text_preview": p.get("text", "")[:100] # Optional: store a preview
            }
            for p in retrieved_passages  # Only include sources that were actually retrieved
        ]

        # 4. Update job status to COMPLETED with result
        update_job_in_db(
            db,
            job_id,
            JobStatus.COMPLETED,
            result_text=generated_answer,
            sources_metadata=sources_for_db,
        )
        task_logger.info("Job successfully completed.")

        total_processing_time = (
            time.time() - start_time_retrieval
        )  # Rough estimate, better to track from task start
        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "processing_time_s": round(total_processing_time, 2),
        }

    except (
        ConnectionError
    ) as exc:  # Specific exception for service connection issues during get_client calls
        task_logger.error(f"A connection error occurred: {exc}", exc_info=True)
        # Update DB to FAILED (already done inside the try block for service init)
        # Retry the task if it's a transient network issue
        try:
            task_logger.info(
                f"Retrying task due to ConnectionError. Attempt {self.request.retries + 1} of {self.max_retries}."
            )
            raise self.retry(
                exc=exc,
                countdown=int(self.default_retry_delay * (self.request.retries + 1)),
            )  # Exponential backoff basic
        except self.MaxRetriesExceededError:
            task_logger.error("Max retries exceeded for task after ConnectionError.")
            update_job_in_db(
                db,
                job_id,
                JobStatus.FAILED,
                result_text=f"Service connection error after retries: {exc}",
            )
            return {"job_id": job_id, "status": "FAILED", "error": str(exc)}

    except Exception as exc:
        task_logger.error(
            f"An unexpected error occurred during task processing: {exc}", exc_info=True
        )
        # Update job status to FAILED in DB
        error_message = f"Processing error: {str(exc)}"
        update_job_in_db(db, job_id, JobStatus.FAILED, result_text=error_message)

        # Retry the task for generic exceptions as well, if configured
        try:
            task_logger.info(
                f"Retrying task due to {type(exc).__name__}. Attempt {self.request.retries + 1} of {self.max_retries}."
            )
            # This will use Celery's retry mechanism based on task decorator args
            raise self.retry(
                exc=exc,
                countdown=int(self.default_retry_delay * (self.request.retries + 1)),
            )
        except self.MaxRetriesExceededError:
            task_logger.error(
                f"Max retries exceeded for task after {type(exc).__name__}."
            )
            # Final update if retries exhausted (already done by last update_job_in_db call before retry attempt)
            return {"job_id": job_id, "status": "FAILED", "error": error_message}
        except Exception as retry_exc:  # Catch errors during the retry call itself
            task_logger.error(
                f"Error occurred while attempting to retry task: {retry_exc}",
                exc_info=True,
            )
            # Job is already marked FAILED, this is a problem with Celery's retry mechanism itself.
            return {
                "job_id": job_id,
                "status": "FAILED",
                "error": f"Retry mechanism failed: {retry_exc}",
            }

    finally:
        db.close()  # Ensure DB session is closed
        task_logger.info("Task finished.")
