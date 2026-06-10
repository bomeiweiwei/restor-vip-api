from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER

from app.core.database import Base


class BookingStay(Base):
    __tablename__ = "BookingStay"

    BookingStayId = Column(
        UNIQUEIDENTIFIER,
        primary_key=True
    )

    CustomerId = Column(
        UNIQUEIDENTIFIER,
        ForeignKey("Customer.CustomerId"),
        nullable=False
    )

    RoomId = Column(
        Integer,
        ForeignKey("Room.RoomId"),
        nullable=False
    )

    CheckInDate = Column(Date)
    CheckOutDate = Column(Date)

    AdultCount = Column(Integer)
    ChildCount = Column(Integer)

    HasParking = Column(Integer)

    CreatedAt = Column(DateTime)
    UpdatedAt = Column(DateTime)