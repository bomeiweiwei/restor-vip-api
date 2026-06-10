from pydantic import BaseModel


class LoginRequest(BaseModel):
    login_account: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    customer_vip_account_id: str
    customer_id: str

    login_account: str

    full_name: str

    email: str | None = None
    mobile_phone: str | None = None

    room_type_name: str | None = None
    room_no: str | None = None