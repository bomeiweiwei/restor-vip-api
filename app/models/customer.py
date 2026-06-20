from sqlalchemy import Column, Unicode, Date, DateTime, String, SmallInteger
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER

from app.core.database import Base


class Customer(Base):
    __tablename__ = "Customer"

    CustomerId = Column(UNIQUEIDENTIFIER, primary_key=True)
    FullName = Column(Unicode(100), nullable=False)
    GenderId = Column(SmallInteger, nullable=False)
    BirthDate = Column(Date, nullable=True)
    CountryCode = Column(Unicode(10), nullable=False)
    MobilePhone = Column(Unicode(30), nullable=True)
    Phone = Column(Unicode(30), nullable=True)
    Email = Column(Unicode(100), nullable=True)
    CreatedAt = Column(DateTime, nullable=False)
    UpdatedAt = Column(DateTime, nullable=False)