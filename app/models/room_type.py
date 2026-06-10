from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class RoomType(Base):
    __tablename__ = "RoomType"

    RoomTypeId = Column(
        Integer,
        primary_key=True
    )

    RoomTypeName = Column(String(100))

    Description = Column(String(500))

    MaxAdultCount = Column(Integer)

    MaxChildCount = Column(Integer)

    IsActive = Column(Boolean)

    CreatedAt = Column(DateTime)
    UpdatedAt = Column(DateTime)