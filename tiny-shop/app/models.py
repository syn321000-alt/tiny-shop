import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text,
    Numeric, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


class TargetType(str, enum.Enum):
    user = "user"
    product = "product"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    # 평문 비밀번호는 절대 저장하지 않는다. 해시만 저장.
    password_hash = Column(String(255), nullable=False)
    bio = Column(String(500), default="")
    balance = Column(Numeric(12, 2), default=0)
    is_admin = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)  # 휴면 계정 여부
    report_count = Column(Integer, default=0)
    failed_login_count = Column(Integer, default=0)  # 로그인 실패 잠금용
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    products = relationship("Product", back_populates="seller")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, default="")
    price = Column(Numeric(12, 2), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_blocked = Column(Boolean, default=False)
    report_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    seller = relationship("User", back_populates="products")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        # 동일 유저가 같은 대상을 반복 신고해서 카운트를 조작하지 못하도록 제한
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uix_report_once"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_type = Column(Enum(TargetType), nullable=False)
    target_id = Column(Integer, nullable=False)
    reason = Column(String(300), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(String(100), nullable=False, index=True)  # "global" 또는 "1_2" 형태
    content = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
