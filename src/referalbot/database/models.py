from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.sql import func
from datetime import datetime
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import select, func

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
    bonus_history = relationship('BonusHistory', back_populates='user', lazy="selectin")

    @hybrid_property
    def total_bonus(self):
        """Python-свойство для доступа к сумме бонусов"""
        return f"{sum(h.amount for h in self.bonus_history) if self.bonus_history else 0}"

    @total_bonus.expression
    def total_bonus(cls):
        """SQL-выражение для вычисления суммы бонусов"""
        return (
            select(func.coalesce(func.sum(BonusHistory.amount), 0))
            .where(BonusHistory.user_id == cls.id)
            .label('total_bonus')
        )

    # Эта функция отвечает за красивое отображение в админке
    def __str__(self) -> str:
        return f"{self.username or 'User'} (ID: {self.id})"
    
    

class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    name = Column(String)
    amount = Column(BigInteger)
    discount_applied = Column(Integer, default=5)
    bonus_amount = Column(BigInteger, nullable=False, default=0)
    date = Column(DateTime, default=datetime.utcnow)
    # bonus_paid = Column(Boolean, default=False) # ЗАКОММЕНТИРОВАЛИ
    
    user = relationship('User', back_populates='purchases')

    def __str__(self) -> str:
        return f"Покупка #{self.id} ({self.name})"

class BonusHistory(Base):
    __tablename__ = 'bonus_history'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    amount = Column(BigInteger)
    operation = Column(String)
    description = Column(String)
    date = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User', back_populates='bonus_history')

    def __str__(self) -> str:
        return f"Операция #{self.id} (user_id={self.user_id})"