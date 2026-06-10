from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, verify_password
from app.models.customer_vip_account import CustomerVipAccount
from app.schemas.auth import LoginRequest, LoginResponse


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def login(self, request: LoginRequest) -> LoginResponse:
        vip_account = (
            self.db.query(CustomerVipAccount)
            .options(joinedload(CustomerVipAccount.customer))
            .filter(CustomerVipAccount.LoginAccount == request.login_account)
            .first()
        )

        if not vip_account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤"
            )

        if not vip_account.IsActive:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此帳號已停用"
            )

        if vip_account.ExpireAt < datetime.now():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此帳號已過期"
            )

        if not verify_password(request.password, vip_account.PasswordHash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤"
            )

        vip_account.LastLoginAt = datetime.now()
        self.db.commit()

        token = create_access_token({
            "sub": str(vip_account.CustomerVipAccountId),
            "customer_id": str(vip_account.CustomerId),
            "login_account": vip_account.LoginAccount,
        })

        customer = vip_account.customer

        return LoginResponse(
            access_token=token,
            customer_vip_account_id=str(vip_account.CustomerVipAccountId),
            customer_id=str(vip_account.CustomerId),
            login_account=vip_account.LoginAccount,
            full_name=customer.FullName,
            email=customer.Email,
            mobile_phone=customer.MobilePhone,
        )