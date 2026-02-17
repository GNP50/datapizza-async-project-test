from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
from msgpack_asgi import MessagePackMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.database import db_manager
from app.services.cache import cache_manager
from app.api import auth, chats, messages, documents
from app.api import settings as settings_router, profile as profile_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application initialization")
    settings = get_settings()

    # Initialize database
    await db_manager.create_tables()

    # Initialize cache
    await cache_manager.connect()

    # Initialize vectorstore
    from app.services.rag.vectorstore import vectorstore
    logger.info("Initializing vectorstore...")
    vectorstore.initialize()

    logger.info("Application initialized successfully")
    yield
    logger.info("Shutting down application")
    await cache_manager.disconnect()
    await db_manager.close()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="AI Chatbot Platform",
    description="Production-ready AI chatbot with fact-checking capabilities",
    version="1.0.0",
    lifespan=lifespan
)

settings = get_settings()

# Add MessagePack middleware for efficient binary serialization
# Temporarily disabled due to encoding conflicts
# app.add_middleware(MessagePackMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Page",
        "X-Page-Size",
        "X-Total-Items",
        "X-Total-Pages",
        "X-Has-Next",
        "X-Has-Previous",
        "Content-Type"
    ],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    logger.info(
        f"Request started",
        extra={
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None
        }
    )

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(
        f"Request completed",
        extra={
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "process_time": f"{process_time:.3f}s"
        }
    )

    return response


app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(documents.router)
app.include_router(settings_router.router)
app.include_router(profile_router.router)


@app.get("/")
async def root():
    return {
        "message": "AI Chatbot Platform API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
