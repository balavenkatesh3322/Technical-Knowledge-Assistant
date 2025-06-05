# app/models/job.py
from sqlalchemy import Column, String, Enum as SAEnum, Text, JSON
from app.models.base import (
    TimestampedModel,
    generate_short_uuid,
)  # Import Base if not using TimestampedModel as direct parent
from app.db.session import Base  # Use the Base from session.py or base.py
import enum


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(TimestampedModel):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_short_uuid)
    question = Column(Text, nullable=False)
    status = Column(
        SAEnum(JobStatus, name="job_status_enum"),
        nullable=False,
        default=JobStatus.PENDING,
    )

    # result can store the generated answer or an error message
    result_text = Column(Text, nullable=True)

    # sources can store a list of dictionaries with source_id, chunk_id, relevance_score, url etc.
    sources_metadata = Column(
        JSON, nullable=True
    )  # Store as JSONB in Postgres for better querying

    # You might want to add more fields, e.g.:
    # error_message = Column(Text, nullable=True)
    # processing_time_seconds = Column(Float, nullable=True)
    # user_id = Column(String, nullable=True) # If you add user context

    def __repr__(self):
        return f"<Job(id={self.id}, status='{self.status}', question='{self.question[:30]}...')>"
