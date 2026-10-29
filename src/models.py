from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base
import uuid
from datetime import UTC, datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Numeric, Uuid, ForeignKey, Integer, Text, UniqueConstraint


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    balance: Mapped[float] = mapped_column(
        Float,
        nullable=True,
        default=0
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="customer",
    )  # 'admin' | 'customer'

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now(UTC),
        nullable=False,
    )
    
    orders: Mapped[list[Orders]] = relationship(back_populates="user")

class Orders(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user: Mapped[User] = relationship(back_populates="orders")
  
