from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import briefing, huddles, intake, memory, onboarding, proposals, suggestion
from app.api.routes import router
from app.config import get_settings

app = FastAPI(
    title="Shepherd API",
    version="0.1.0",
    description="Shepherd suggests, a person decides.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(onboarding.router)
app.include_router(proposals.router)
app.include_router(intake.router)
app.include_router(briefing.router)
app.include_router(huddles.router)
app.include_router(memory.router)
app.include_router(suggestion.router)
