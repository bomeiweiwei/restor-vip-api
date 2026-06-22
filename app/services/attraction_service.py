from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.attraction import AttractionResponse


class AttractionService:
    def get_recommended_attractions(
        self,
        db: Session,
        current_user: dict,
    ) -> list[AttractionResponse]:
        
        customer_vip_account_id = current_user.get("sub")
        customer_id = current_user.get("customer_id")
        login_account = current_user.get("login_account")

        sql = text("""
            SELECT DISTINCT
                CONVERT(nvarchar(100), vs.Title) AS attraction_id,
                vs.Title AS place_name,
                vs.Preference AS category,
                vs.Latitude AS latitude,
                vs.Longitude AS longitude
            FROM VipItineraryRecommendation vr
            INNER JOIN VipItinerarySchedule vs
                ON vr.RecommendationId = vs.RecommendationId
            INNER JOIN Customer c
                ON vr.CustomerId = c.CustomerId
            INNER JOIN CustomerVipAccount cva
                ON c.CustomerId = cva.CustomerId
            WHERE
                c.CustomerId = :customer_id
                AND cva.CustomerVipAccountId = :customer_vip_account_id
                AND cva.LoginAccount = :login_account
                AND vs.Latitude IS NOT NULL
                AND vs.Longitude IS NOT NULL
        """)

        rows = db.execute(
            sql,
            {
                "customer_id": customer_id,
                "customer_vip_account_id": customer_vip_account_id,
                "login_account": login_account,
            },
        ).mappings().all()

        return [
            AttractionResponse(
                attraction_id=row["attraction_id"],
                place_name=row["place_name"],
                category=row["category"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            for row in rows
        ]


attraction_service = AttractionService()