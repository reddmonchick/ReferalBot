from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy import BigInteger
from datetime import datetime

Base = declarative_base(cls=AsyncAttrs)

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    username = Column(String, nullable=True)
    promo_code = Column(String, unique=True)
    invited_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    invited_by = relationship('User', remote_side=[id], back_populates='referrals')
    referrals = relationship('User', back_populates='invited_by', foreign_keys=[invited_by_id])

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    amount = Column(BigInteger)  # Сумма в IDR, целое число
    date = Column(DateTime, default=datetime.utcnow)
    bonus_paid = Column(Boolean, default=False)
    user = relationship('User')