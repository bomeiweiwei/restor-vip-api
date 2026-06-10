from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey

from app.core.database import Base


class Room(Base):
    __tablename__ = "Room"

    RoomId = Column(
        Integer,
        primary_key=True
    )

    RoomTypeId = Column(
        Integer,
        ForeignKey("RoomType.RoomTypeId"),
        nullable=False
    )

    RoomNo = Column(String(20))

    FloorNo = Column(Integer)

    IsActive = Column(Boolean)

    CreatedAt = Column(DateTime)
    UpdatedAt = Column(DateTime)