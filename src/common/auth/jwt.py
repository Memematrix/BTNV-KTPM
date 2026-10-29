import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from src.common.config import settings

from uuid import UUID
import jwt as pyjwt

JWT_SECRET_KEY = settings.secret_key.get_secret_value()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = settings.jwt_expire_minutes


class TokenPayload:
    def __init__(self, user_id: UUID, role: str):
        self.id = user_id
        self.role = role

    def __repr__(self) -> str:
        return f"TokenPayload(id={self.id!r}, role={self.role!r})"


def create_access_token(user_id: UUID, role: str, expires_minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    expire_delta = timedelta(
        minutes=expires_minutes if expires_minutes is not None else JWT_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),        # subject — quy ước chuẩn JWT để lưu id chủ thể token
        "role": role,
        "iat": now,                 # issued at
        "exp": now + expire_delta,  # expiry
    }

    return pyjwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> TokenPayload:
    try:
        payload = pyjwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    role = payload.get("role")

    user_id = UUID(user_id)

    if user_id is None or role is None:
        raise pyjwt.InvalidTokenError("Token thiếu field 'sub' hoặc 'role'")

    return TokenPayload(user_id=user_id, role=role)