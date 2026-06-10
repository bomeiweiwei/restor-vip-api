from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, LoginResponse

from app.models.customer import Customer
from app.models.customer_vip_account import CustomerVipAccount
from app.models.booking_stay import BookingStay
from app.models.room import Room
from app.models.room_type import RoomType


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def login(self, request: LoginRequest) -> LoginResponse:
        result = (
            self.db.query(
                CustomerVipAccount,
                Customer,
                RoomType.RoomTypeName,
                Room.RoomNo,
            )
            .join(
                Customer,
                CustomerVipAccount.CustomerId == Customer.CustomerId,
            )
            .outerjoin(
                BookingStay,
                Customer.CustomerId == BookingStay.CustomerId,
            )
            .outerjoin(
                Room,
                BookingStay.RoomId == Room.RoomId,
            )
            .outerjoin(
                RoomType,
                Room.RoomTypeId == RoomType.RoomTypeId,
            )
            .filter(CustomerVipAccount.LoginAccount == request.login_account)
            .first()
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
            )

        vip_account, customer, room_type_name, room_no = result

        if not vip_account.IsActive:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此帳號已停用",
            )

        if vip_account.ExpireAt < datetime.now():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此帳號已過期",
            )

        if not verify_password(request.password, vip_account.PasswordHash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
            )

        vip_account.LastLoginAt = datetime.now()
        self.db.commit()

        access_token = create_access_token(
            {
                "sub": str(vip_account.CustomerVipAccountId),
                "customer_id": str(vip_account.CustomerId),
                "login_account": vip_account.LoginAccount,
            }
        )

        return LoginResponse(
            access_token=access_token,
            customer_vip_account_id=str(vip_account.CustomerVipAccountId),
            customer_id=str(vip_account.CustomerId),
            login_account=vip_account.LoginAccount,
            full_name=customer.FullName,
            email=customer.Email,
            mobile_phone=customer.MobilePhone,
            room_type_name=room_type_name,
            room_no=room_no,
        )
