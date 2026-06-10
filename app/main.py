from fastapi import FastAPI

from app.api.auth_router import router as auth_router

app = FastAPI(
    title="Resort VIP API",
    version="1.0.0",
)

app.include_router(auth_router)


@app.get("/")
def root():
    return {
        "message": "Resort VIP API Running"
    }