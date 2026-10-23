import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import logger
from app.api.v1.api import api_v1_router
from app.api.v1.health import router as health_router
from app.workers.webhook_worker import run_worker_loop, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist
    logger.info("Initializing SIM SMS Gateway backend...")
    init_db()
    logger.info("Database schemas initialized.")

    # Launch background worker
    worker_task = asyncio.create_task(run_worker_loop(interval_seconds=3.0))

    yield

    # Shutdown
    logger.info("Shutting down background workers...")
    stop_worker()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade SIM SMS Gateway API. Turns an Android phone with a SIM card "
        "into a high-reliability SMS gateway with database-backed job queues, device pairing, "
        "and signed HMAC-SHA256 webhook dispatch."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID & Audit Middleware
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact system administrator."},
    )


# Mount routers
app.include_router(health_router)  # /health
app.include_router(api_v1_router, prefix=settings.API_V1_STR)  # /api/v1/...
