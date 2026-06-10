from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_router import router as auth_router
from app.api.assistant_router import router as assistant_router
from app.api.itinerary_router import router as itinerary_router

from app.core.config import settings

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


@app.get("/")
def root():
    return {
        "message": "Resort VIP API Running"
    }