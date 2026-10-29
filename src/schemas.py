from pydantic import BaseModel, ConfigDict, Field, field_validator
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from typing import Literal



class OrderBase(BaseModel):
    status: str = Field(default="pending")


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)


class OrderResponse(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    total_amount: Decimal
    created_at: datetime

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value

class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    phone: Optional[str] = None
    role: str
    created_at: datetime
    
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AvatarUploadRequest(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/png"


class AvatarUploadResponse(BaseModel):
    upload_url: str
    method: str = "PUT"
    object_key: str
    expires_in: int = 300
    headers: dict[str, str]


class AvatarDownloadResponse(BaseModel):
    download_url: str
    expires_in: int = 300


class DashboardResponse(BaseModel):
    user: UserResponse
    orders: list[OrderResponse]
