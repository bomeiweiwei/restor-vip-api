from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_router import router as auth_router
from app.api.assistant_router import router as assistant_router
from app.api.itinerary_router import router as itinerary_router
from app.api.attraction_router import router as attraction_router

from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Resort VIP API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_ORIGIN,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(itinerary_router)
app.include_router(attraction_router)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


@app.get("/")
def root():
    return {
        "message": "Resort VIP API Running"
    }