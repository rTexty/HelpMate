from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    BigInteger,
    ForeignKey,
    Text,
    TIMESTAMP,
    Numeric
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    full_name = Column(String(255))
    preferred_name = Column(String(255))
    age = Column(Integer)
    gender = Column(String(10))
    status = Column(String(50), default='demo')
    subscription_until = Column(TIMESTAMP(timezone=True))
    daily_message_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    onboarding_completed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_activity = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Prompt(Base):
    __tablename__ = 'prompts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class TextSettings(Base):
    __tablename__ = 'text_settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    description = Column(String(255))

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_system = Column(String(50), nullable=False)
    status = Column(String(50), default='pending')
    telegram_payment_charge_id = Column(Text)
    cryptocloud_invoice_id = Column(String(255))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()) 