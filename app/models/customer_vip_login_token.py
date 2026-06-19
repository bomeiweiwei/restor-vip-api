from sqlalchemy import Column, Unicode, DateTime, String
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER

from app.core.database import Base


class CustomerVipLoginToken(Base):
    __tablename__ = "CustomerVipLoginToken"

    TokenId = Column(UNIQUEIDENTIFIER, primary_key=True)

    CustomerVipAccountId = Column(
        UNIQUEIDENTIFIER,
        nullable=False,
    )

    TokenHash = Column(
        Unicode(255),
        nullable=False,
    )

    ExpireAt = Column(
        DateTime,
        nullable=False,
    )

    UsedAt = Column(
        DateTime,
        nullable=True,
    )

    CreatedAt = Column(
        DateTime,
        nullable=False,
    )