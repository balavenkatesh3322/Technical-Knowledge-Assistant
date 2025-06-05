# app/api/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import datetime
from app.models.job import JobStatus  # Import Enum for validation


class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, max_length=1000, description="The technical question to ask."
    )

    @field_validator("question")
    def question_must_not_be_empty(cls, value):
        if not value.strip():
            raise ValueError("Question cannot be empty or just whitespace.")
        return value


class JobBase(BaseModel):
    id: str = Field(description="Unique identifier for the job.")
    question: str = Field(description="The original question submitted.")
    status: JobStatus = Field(description="Current status of the job.")
    created_at: datetime.datetime = Field(
        description="Timestamp when the job was created."
    )
    updated_at: datetime.datetime = Field(
        description="Timestamp when the job was last updated."
    )


class JobCreateResponse(BaseModel):
    job_id: str = Field(description="Unique identifier for the created job.")
    status: JobStatus = Field(description="Initial status of the job (PENDING).")
    message: str = Field(
        default="Job accepted and queued for processing.",
        description="A message confirming job acceptance.",
    )


class SourceDocument(BaseModel):
    source_id: Optional[str] = Field(
        None,
        description="Identifier of the source document (e.g., article title, file name).",
    )
    chunk_id: Optional[str] = Field(
        None, description="Identifier of the specific chunk within the source document."
    )
    relevance_score: Optional[float] = Field(
        None, description="Relevance score of this source to the answer."
    )
    url: Optional[str] = Field(
        None, description="URL or path to the source document, if available."
    )
    # You can add more fields like page_number, snippet_from_source, etc.


class JobResultResponse(JobBase):
    result_text: Optional[str] = Field(
        None,
        description="The generated answer to the question, or an error message if failed.",
    )
    sources_metadata: Optional[List[SourceDocument]] = Field(
        None, description="List of source documents that contributed to the answer."
    )
    processing_time_seconds: Optional[float] = Field(
        None, description="Approximate time taken to process the job, if available."
    )


# For internal use or more detailed API responses if needed
class JobInDB(JobBase):
    result_text: Optional[str] = None
    sources_metadata: Optional[List[Dict[str, Any]]] = None  # Stored as JSON in DB

    class Config:
        from_attributes = True  # for Pydantic v2, or orm_mode = True for v1
