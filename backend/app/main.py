from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ask,
    briefing,
    chat,
    demo,
    huddles,
    intake,
    memory,
    onboarding,
    proposals,
    suggestion,
)
from app.api.errors import register_error_handlers
from app.api.routes import router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """With RUN_SCHEDULER on, the nightly job runs inside this process (ADR 0002)."""
    scheduler = None
    if get_settings().run_scheduler:
        from app.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Shepherd API",
    version="0.1.0",
    description="Shepherd suggests, a person decides.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(router)
app.include_router(onboarding.router)
app.include_router(proposals.router)
app.include_router(intake.router)
app.include_router(briefing.router)
app.include_router(huddles.router)
app.include_router(memory.router)
app.include_router(suggestion.router)
app.include_router(ask.router)
app.include_router(chat.router)
app.include_router(demo.router)
