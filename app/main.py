"""Content Registry - FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import MAX_FILE_SIZE, UPLOADS_DIR
from app.database import init_db
from app.routers import content, metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(
    title="Content Registry",
    description=(
        "A microservice for uploading and classifying educational content.\n\n"
        "Upload files, tag them by **Class**, **Subject**, and **Chapter**, "
        "and retrieve them with powerful filters.\n\n"
        "Designed to be agent-friendly for future knowledge graph integration."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Upload size guard middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Reject requests that declare a body larger than MAX_FILE_SIZE."""
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_FILE_SIZE:
            return Response(
                content=f"Request too large. Max allowed: {MAX_FILE_SIZE // (1024 * 1024)} MB",
                status_code=413,
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# CORS — restrict to env-var origins in production
# ---------------------------------------------------------------------------

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(content.router)
app.include_router(metadata.router)

# Serve uploaded files as static (for download links in extracted markdown)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check for load balancers and container orchestrators."""
    return {"status": "ok", "service": "content-registry"}


@app.get("/", tags=["Health"])
async def root():
    """Service info / root endpoint."""
    return {
        "service": "Content Registry",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }
