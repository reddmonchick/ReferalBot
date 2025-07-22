from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Computed, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.sql import func
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
    purchases = relationship('Purchase', back_populates='user')
class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    name = Column(String)
    amount = Column(BigInteger)  # Сумма в IDR
    discount_applied = Column(Integer, default=5)  # Скидка в процентах (по умолчанию 5%)
    bonus_amount = Column(BigInteger, nullable=False, default=0)  # 5% бонус
    date = Column(DateTime, default=datetime.utcnow)
    bonus_paid = Column(Boolean, default=False)
    user = relationship('User', back_populates='purchases')