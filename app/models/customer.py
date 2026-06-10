from sqlalchemy import Column, Date, DateTime, String, SmallInteger
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER

from app.core.database import Base


class Customer(Base):
    __tablename__ = "Customer"

    CustomerId = Column(UNIQUEIDENTIFIER, primary_key=True)
    FullName = Column(String(100), nullable=False)
    GenderId = Column(SmallInteger, nullable=False)
    BirthDate = Column(Date, nullable=True)
    CountryCode = Column(String(10), nullable=False)
    MobilePhone = Column(String(30), nullable=True)
    Phone = Column(String(30), nullable=True)
    Email = Column(String(100), nullable=True)
    CreatedAt = Column(DateTime, nullable=False)
    UpdatedAt = Column(DateTime, nullable=False)