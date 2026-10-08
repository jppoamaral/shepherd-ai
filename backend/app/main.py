from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Shepherd API",
    version="0.1.0",
    description="Shepherd suggests, a person decides.",
)
app.include_router(router)
