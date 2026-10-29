from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional



class OrderBase(BaseModel):
    status: str = Field(default="pending")


class OrderCreate(BaseModel):
    user_id: uuid.UUID


class OrderResponse(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    total_amount: Decimal
    created_at: datetime

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=255)
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)

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