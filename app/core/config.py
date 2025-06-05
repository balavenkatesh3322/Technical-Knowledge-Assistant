# app/core/config.py
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Optional

# Load .env file from the project root
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Technical Knowledge Assistant")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8080"))

    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://redis:6379/0"
    )

    # Database (PostgreSQL)
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "postgres_db")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "knowledge_assistant_db")

    # Construct DATABASE_URL ensuring default values are used if specific parts are not in .env
    # This prioritizes DATABASE_URL if it's explicitly set in .env
    _db_user = POSTGRES_USER
    _db_password = POSTGRES_PASSWORD
    _db_server = POSTGRES_SERVER
    _db_port = POSTGRES_PORT
    _db_name = POSTGRES_DB

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{_db_user}:{_db_password}@{_db_server}:{_db_port}/{_db_name}",
    )

    # Vector Database
    VECTOR_DB_IMPL: str = os.getenv(
        "VECTOR_DB_IMPL", "chromadb"
    )  # e.g., "chromadb", "faiss"
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "vector_db")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
    CHROMA_COLLECTION_NAME: str = os.getenv(
        "CHROMA_COLLECTION_NAME", "simple_wikipedia_chunks"
    )
    # FAISS_INDEX_PATH: Optional[str] = os.getenv("FAISS_INDEX_PATH")
    # FAISS_METADATA_PATH: Optional[str] = os.getenv("FAISS_METADATA_PATH")

    # LLM and Embeddings
    LLM_MODEL_NAME: str = os.getenv(
        "LLM_MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.1"
    )
    LLM_MODEL_PATH: Optional[str] = os.getenv(
        "LLM_MODEL_PATH"
    )  # For locally stored models
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # Data Ingestion
    DATASET_NAME: str = os.getenv("DATASET_NAME", "rahular/simple-wikipedia")
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", 512))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", 64))

    # Retrieval
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", 5))

    # Hugging Face Hub Token
    HUGGING_FACE_HUB_TOKEN: Optional[str] = os.getenv("HUGGING_FACE_HUB_TOKEN")

    # Prometheus / Monitoring
    PROMETHEUS_ENABLED: bool = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"

    # Rate Limiting (example, adjust as needed)
    RATE_LIMIT_TIMES: int = int(os.getenv("RATE_LIMIT_TIMES", "100"))
    RATE_LIMIT_SECONDS: int = int(os.getenv("RATE_LIMIT_SECONDS", "60"))  # Per minute

    # CORS Origins (for FastAPI) - example
    BACKEND_CORS_ORIGINS: List[str] = [
        origin.strip() for origin in os.getenv("BACKEND_CORS_ORIGINS", "*").split(",")
    ]


settings = Settings()

# You can add more specific settings classes if needed, e.g., for different environments
# class DevelopmentSettings(Settings):
#     LOG_LEVEL: str = "DEBUG"

# class ProductionSettings(Settings):
#     LOG_LEVEL: str = "INFO"

# Add logic here to select settings based on an environment variable like APP_ENV
# For simplicity, we're directly using the Settings class.
