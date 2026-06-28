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
from app.models.customer_vip_login_token import CustomerVipLoginToken


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
            country_code=customer.CountryCode
        )

    def vip_magic_login(self, token: str):
        now = datetime.now()

        tokens = (
            self.db.query(CustomerVipLoginToken)
            .filter(CustomerVipLoginToken.UsedAt == None)
            .filter(CustomerVipLoginToken.ExpireAt > now)
            .all()
        )

        matched_token = None

        for db_token in tokens:
            if verify_password(token, db_token.TokenHash):
                matched_token = db_token
                break

        if matched_token is None:
            raise HTTPException(status_code=401, detail="登入連結無效或已過期")

        vip_account = (
            self.db.query(CustomerVipAccount)
            .filter(
                CustomerVipAccount.CustomerVipAccountId
                == matched_token.CustomerVipAccountId
            )
            .filter(CustomerVipAccount.IsActive == True)
            .filter(CustomerVipAccount.ExpireAt > now)
            .first()
        )

        if vip_account is None:
            raise HTTPException(status_code=401, detail="VIP帳號無效或已過期")

        matched_token.UsedAt = now
        self.db.commit()

        access_token = create_access_token(
            {
                "sub": str(vip_account.CustomerVipAccountId),
                "customer_id": str(vip_account.CustomerId),
                "login_account": vip_account.LoginAccount,
            }
        )

        profile = (
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
            .filter(CustomerVipAccount.LoginAccount == vip_account.LoginAccount)
            .first()
        )
        _, customer, room_type_name, room_no = profile

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "customer_vip_account_id": str(vip_account.CustomerVipAccountId),
            "customer_id": str(vip_account.CustomerId),
            "login_account": vip_account.LoginAccount,
            "full_name": customer.FullName,
            "email": customer.Email,
            "mobile_phone": customer.MobilePhone,
            "room_type_name": room_type_name,
            "room_no": room_no,
            "country_code":customer.CountryCode
        }
