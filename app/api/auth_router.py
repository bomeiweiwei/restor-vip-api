from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse, VipMagicLoginRequest
from app.services.auth_service import AuthService


router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"]
)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    return service.login(request)

@router.post("/vip-login")
def vip_magic_login(
    request: VipMagicLoginRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    return service.vip_magic_login(request.token)