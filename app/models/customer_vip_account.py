from sqlalchemy import Boolean, Unicode, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.customer import Customer


class CustomerVipAccount(Base):
    __tablename__ = "CustomerVipAccount"

    CustomerVipAccountId = Column(UNIQUEIDENTIFIER, primary_key=True)
    CustomerId = Column(
        UNIQUEIDENTIFIER,
        ForeignKey("Customer.CustomerId"),
        nullable=False
    )
    LoginAccount = Column(Unicode(10), nullable=False, unique=True)
    PasswordHash = Column(Unicode(255), nullable=False)
    IsActive = Column(Boolean, nullable=False)
    ExpireAt = Column(DateTime, nullable=False)
    LastLoginAt = Column(DateTime, nullable=True)
    CreatedAt = Column(DateTime, nullable=False)
    UpdatedAt = Column(DateTime, nullable=False)

    customer = relationship(Customer)