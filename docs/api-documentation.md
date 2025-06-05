# API Service Documentation

## Overview
This document provides an explanation of the API architecture, detailing the components, their interactions, and the flow of requests through the system.

## Architecture Diagram Explanation

### Components

#### User/Client
- **Description**: The entity initiating requests to the API, such as a web frontend, mobile app, or curl commands.

#### API Gateway (Conceptual)
- **Description**: In a production environment, an API Gateway (e.g., Nginx, HAProxy, or a cloud provider's service) would handle load balancing, SSL termination, advanced rate limiting, and authentication. Note: Not explicitly implemented in this simple setup.

#### API Service (FastAPI)
- **Description**: The core service handling RESTful API requests.
- **Endpoints**:
  - `POST /api/v1/ask`: Submits a new question/task.
  - `GET /api/v1/ask/{id}`: Retrieves the status or results of a specific job by ID.
  - `GET /metrics`: Exposes metrics for Prometheus monitoring.
  - `GET /health`: Checks connectivity to critical services (e.g., database).
- **Internal Logic**:
  - **Request Validation**: Ensures incoming data is correctly formatted and contains required information.
  - **Job ID Generation**: Creates a unique identifier for each new task.
  - **Database Interaction**: Communicates with the PostgreSQL JobStore to create job entries and retrieve job status/results.
  - **Task Enqueueing**: Pushes tasks (question and job ID) to the Celery task queue (Redis).
  - **Metrics Collection**: Gathers and exposes metrics for Prometheus.

#### Backend Services
- **JobDB (PostgreSQL)**:
  - Stores persistent data related to jobs, such as job IDs, statuses, and results.
- **TaskQueue (Redis)**:
  - Acts as the message broker for Celery tasks, queuing tasks for processing.
- **Prometheus Server**:
  - Scrapes the `/metrics` endpoint of the API to collect and monitor performance metrics.

### Request Flow
1. **User Request**: A user sends a request to an API endpoint (e.g., `POST /api/v1/ask`).
2. **Request Validation**: The API validates the incoming request for correct format and required data.
3. **Task Processing** (for `/ask`):
   - A unique job ID is generated.
   - A new job entry is created in the JobDB (PostgreSQL).
   - The task (question and job ID) is enqueued in the TaskQueue (Redis).
4. **API Response**:
   - For `POST /api/v1/ask`, the API returns the job ID.
   - For `GET /api/v1/ask/{id}`, the API returns job details (status/results) from the JobDB.
5. **Monitoring**:
   - The `/metrics` endpoint is periodically scraped by the Prometheus server.
   - The `/health` endpoint checks connectivity to critical services like the database.

## API Sequence Diagram

![API Diagram](./images/APISequenceDiagram.png)

### Mermaid code
```mermaid
sequenceDiagram
    participant Client as Client Application
    participant Gateway as API Gateway
    participant API as FastAPI Service
    participant DB as PostgreSQL
    participant Redis as Redis Queue
    participant Worker as Celery Worker
    participant Vector as ChromaDB
    participant DocStore as Document Store
    participant LLM as LLM Service
    participant Metrics as Prometheus

    Note over Client, Metrics: RAG System - Complete API Flow

    %% Submit Question Flow
    rect rgb(240, 248, 255)
        Note over Client, Redis: 1. Question Submission Flow
        Client->>+Gateway: POST /api/v1/ask
        Note right of Client: {"question": "What is...?"}
        
        Gateway->>+API: Route request
        API->>API: Validate request
        API->>API: Generate job_id
        API->>+DB: INSERT job (job_id, question, status='PENDING')
        DB-->>-API: Job created
        API->>+Redis: Enqueue task (job_id, question)
        Redis-->>-API: Task queued
        API-->>-Gateway: {"job_id": "uuid", "status": "PENDING"}
        Gateway-->>-Client: HTTP 202 - Job accepted
    end

    %% Background Processing Flow
    rect rgb(248, 255, 248)
        Note over Redis, LLM: 2. Background Processing Flow
        Redis->>+Worker: Assign task
        Worker->>+DB: UPDATE job status='PROCESSING'
        DB-->>-Worker: Status updated
        
        %% Retrieval Phase
        Note over Worker, DocStore: Retrieval Phase
        Worker->>+DocStore: Keyword search query
        DocStore-->>-Worker: Relevant documents (keyword)
        
        Worker->>Worker: Generate question embedding
        Worker->>+Vector: Semantic search (embedding)
        Vector-->>-Worker: Relevant documents (semantic)
        
        Worker->>Worker: Combine & rank results
        
        %% Generation Phase
        Note over Worker, LLM: Generation Phase
        Worker->>Worker: Build context prompt
        Worker->>+LLM: Generate answer with context
        LLM-->>-Worker: Generated response
        
        Worker->>+DB: UPDATE job (answer, citations, status='COMPLETED')
        DB-->>-Worker: Job completed
    end

    %% Status Polling Flow
    rect rgb(255, 248, 240)
        Note over Client, DB: 3. Status Polling Flow
        Client->>+Gateway: GET /api/v1/ask/{job_id}
        Gateway->>+API: Route request
        API->>+DB: SELECT job WHERE job_id=?
        DB-->>-API: Job details
        API-->>-Gateway: {"job_id": "uuid", "status": "COMPLETED", "answer": "...", "citations": [...]}
        Gateway-->>-Client: HTTP 200 - Complete response
    end

    %% Health Check Flow
    rect rgb(255, 240, 255)
        Note over Client, DB: 4. Health Check Flow
        Client->>+Gateway: GET /health
        Gateway->>+API: Route request
        API->>+DB: SELECT 1 (health check)
        DB-->>-API: Connection OK
        API->>+Redis: PING
        Redis-->>-API: PONG
        API-->>-Gateway: {"status": "healthy", "database": "ok", "redis": "ok"}
        Gateway-->>-Client: HTTP 200 - System healthy
    end

    %% Metrics Collection Flow
    rect rgb(248, 248, 255)
        Note over Metrics, API: 5. Metrics Collection Flow
        Metrics->>+API: GET /metrics
        API->>API: Collect application metrics
        API-->>-Metrics: Prometheus format metrics
        Note right of Metrics: Request counts, latency, etc.
    end

    %% Error Handling Flow
    rect rgb(255, 248, 248)
        Note over Worker, DB: 6. Error Handling Flow
        alt Processing Error
            Worker->>Worker: Exception during processing
            Worker->>+DB: UPDATE job (error_msg, status='FAILED')
            DB-->>-Worker: Status updated
        end
        
        alt Polling Failed Job
            Client->>+Gateway: GET /api/v1/ask/{job_id}
            Gateway->>+API: Route request
            API->>+DB: SELECT job WHERE job_id=?
            DB-->>-API: Job with FAILED status
            API-->>-Gateway: {"job_id": "uuid", "status": "FAILED", "error": "..."}
            Gateway-->>-Client: HTTP 200 - Error response
        end
    end
```

