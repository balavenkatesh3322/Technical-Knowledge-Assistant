# app/api/main.py
from fastapi import FastAPI, Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware  # For CORS
from app.core.config import settings
from app.core.logging_config import setup_logging, CustomJsonFormatter
from app.api.routers import ask as ask_router
from app.api.dependencies import get_db_health  # For health check
from app.db.session import engine as db_engine, Base as db_base  # For creating tables
from prometheus_fastapi_instrumentator import Instrumentator  # For Prometheus
import logging
import time  # For request timing example

# Call setup_logging() early, before creating FastAPI app or importing other modules that log
setup_logging()
logger = logging.getLogger(__name__)


# Create database tables if they don't exist (Alembic is preferred for production)
# This is a simple way for development, but for production, use Alembic migrations.
def create_db_tables():
    logger.info("Attempting to create database tables if they don't exist...")
    try:
        if db_engine:
            db_base.metadata.create_all(bind=db_engine)
            logger.info("Database tables checked/created successfully.")
        else:
            logger.error("Database engine is not initialized. Cannot create tables.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}", exc_info=True)
        # Depending on the setup, you might want to exit or raise a critical error.


# Call it at startup. In a more complex setup, this might be a startup event.
create_db_tables()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"/api/v1/openapi.json",  # Customize OpenAPI URL
    # docs_url="/api/docs",  # Default is /docs
    # redoc_url="/api/redoc" # Default is /redoc
    # version="0.1.0" # Add versioning
)

# --- Prometheus Instrumentation ---
if settings.PROMETHEUS_ENABLED:
    # Exposes /metrics endpoint
    Instrumentator().instrument(app).expose(
        app, include_in_schema=True, tags=["Monitoring"]
    )
    logger.info("Prometheus instrumentation enabled and /metrics endpoint exposed.")


# --- CORS Middleware ---
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )
    logger.info(f"CORS middleware enabled for origins: {settings.BACKEND_CORS_ORIGINS}")


# --- Custom Request Logging Middleware (Example) ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    # Log request details before processing
    # logger.info(f"Incoming request: {request.method} {request.url.path}", extra={"client_host": request.client.host})

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000  # milliseconds
    formatted_process_time = "{0:.2f}".format(process_time)

    # Log response details after processing
    # Using a custom log record structure for JSON logger
    log_extra = {
        "client_host": request.client.host,
        "request_method": request.method,
        "request_path": request.url.path,
        "response_status_code": response.status_code,
        "response_process_time_ms": formatted_process_time,
    }
    logger.info(
        f"Request {request.method} {request.url.path} completed with status {response.status_code}",
        extra=log_extra,
    )

    return response


# --- Custom Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the validation error in more detail
    logger.warning(
        f"Request validation error: {exc.errors()}",
        extra={
            "client_host": request.client.host,
            "request_path": request.url.path,
            "detail": exc.errors(),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "message": "Validation failed for one or more fields.",
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Log HTTP exceptions
    logger.error(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "client_host": request.client.host,
            "request_path": request.url.path,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)  # Generic fallback
async def generic_exception_handler(request: Request, exc: Exception):
    logger.critical(
        f"Unhandled exception: {exc}",
        exc_info=True,  # Include stack trace
        extra={"client_host": request.client.host, "request_path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )


# --- Routers ---
app.include_router(ask_router.router, prefix="/api/v1")  # Add a version prefix
logger.info("Ask router included with prefix /api/v1/ask")


# --- Health Check Endpoint ---
@app.get("/health", tags=["Monitoring"], status_code=status.HTTP_200_OK)
async def health_check(db_healthy: bool = Depends(get_db_health)):
    # Basic health check, can be expanded (e.g., check Celery connection)
    api_status = {"status": "ok", "message": "API is running"}
    services = {"database": "healthy" if db_healthy else "unhealthy"}

    if not db_healthy:
        logger.warning("Health check: Database service is unhealthy.")
        # Return 503 if critical dependencies are down
        # raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"api": api_status, "services": services})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"api_status": api_status, "services": services},
        )

    logger.info("Health check: API and Database are healthy.")
    return {"api_status": api_status, "services": services}


# --- Startup and Shutdown Events (Optional) ---
@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application startup commencing...")
    # Example: Initialize ML models if not done elsewhere, connect to services
    # Note: DB tables are created above, outside of event for simplicity here
    logger.info("FastAPI application started successfully.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI application shutdown commencing...")
    # Example: Clean up resources, close connections
    if db_engine:
        db_engine.dispose()  # Close all database connections in the pool
        logger.info("Database engine connections disposed.")
    logger.info("FastAPI application shutdown completed.")


if __name__ == "__main__":
    # This block is for local development without Docker/Uvicorn CLI directly
    # Uvicorn is typically run by docker-compose command or directly via CLI for production
    import uvicorn

    logger.info(
        f"Starting Uvicorn server directly on {settings.API_HOST}:{settings.API_PORT} with log level {settings.LOG_LEVEL}"
    )
    uvicorn.run(
        "main:app",  # Points to this file (main.py) and the app object
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),  # Uvicorn expects lowercase log level
        reload=True,  # Enable reload for development
    )
