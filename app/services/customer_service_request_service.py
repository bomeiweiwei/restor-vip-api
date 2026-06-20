from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.assistant import AssistantResponse


class CustomerServiceRequestService:

    def process(
        self,
        db: Session,
        current_user: dict,
        message: str,
    ) -> AssistantResponse:

        customer_vip_account_id = current_user.get("sub")
        customer_id = current_user.get("customer_id")
        login_account = current_user.get("login_account")

        # 取得目前最新住宿資料、房號、旅客姓名
        stay = db.execute(
            text("""
                SELECT TOP 1
                    bs.BookingStayId,
                    r.RoomId,
                    r.RoomNo,
                    c.FullName AS CustomerName
                FROM BookingStay bs
                INNER JOIN Room r
                    ON bs.RoomId = r.RoomId
                INNER JOIN Customer c
                    ON bs.CustomerId = c.CustomerId
                WHERE bs.CustomerId = :customer_id
                ORDER BY bs.CheckInDate DESC
            """),
            {
                "customer_id": customer_id,
            },
        ).mappings().first()

        # 產生需求編號：REQ-000001
        next_no = db.execute(
            text("""
                SELECT ISNULL(MAX(CAST(SUBSTRING(RequestNo, 5, 6) AS INT)), 0) + 1
                FROM CustomerServiceRequest
                WHERE RequestNo LIKE 'REQ-%'
            """)
        ).scalar()

        request_no = f"REQ-{next_no:06d}"

        db.execute(
            text("""
                INSERT INTO CustomerServiceRequest
                (
                    RequestNo,
                    CustomerVipAccountId,
                    CustomerId,
                    LoginAccount,
                    BookingStayId,
                    RoomId,
                    RoomNo,
                    CustomerName,
                    Message,
                    Status,
                    PriorityLevel,
                    CreatedAt
                )
                VALUES
                (
                    :request_no,
                    :customer_vip_account_id,
                    :customer_id,
                    :login_account,
                    :booking_stay_id,
                    :room_id,
                    :room_no,
                    :customer_name,
                    :message,
                    'Pending',
                    'Normal',
                    SYSUTCDATETIME()
                )
            """),
            {
                "request_no": request_no,
                "customer_vip_account_id": customer_vip_account_id,
                "customer_id": customer_id,
                "login_account": login_account,
                "booking_stay_id": stay["BookingStayId"] if stay else None,
                "room_id": stay["RoomId"] if stay else None,
                "room_no": stay["RoomNo"] if stay else None,
                "customer_name": stay["CustomerName"] if stay else None,
                "message": message,
            },
        )

        db.commit()

        print('=====Customer Service Request=====')

        return AssistantResponse(
            reply=(
                f"已收到您的需求：{message}\n"
                f"需求編號：{request_no}"
            )
        )


customer_service_request_service = CustomerServiceRequestService()