from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException

from src.common.config import settings


@dataclass(frozen=True)
class TokenPayload:
    id: UUID
    role: str


def create_access_token(user_id: UUID, role: str, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(
                minutes=settings.jwt_expire_minutes if expires_minutes is None else expires_minutes
            ),
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def verify_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        user_id = UUID(payload["sub"])
        role = payload["role"]
        if role not in {"customer", "admin"}:
            raise ValueError("Invalid role")
        return TokenPayload(id=user_id, role=role)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
