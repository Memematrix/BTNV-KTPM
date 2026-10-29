import decimal
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, default=0)
    role: Mapped[str] = mapped_column(String(20), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Orders(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The User service owns its database. Ownership comes from the authenticated identity.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
