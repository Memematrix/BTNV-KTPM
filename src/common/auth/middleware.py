import secrets
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.common.config import settings
from .jwt import TokenPayload as CurrentUser, verify_access_token

__all__ = ["get_current_user", "get_page_user", "CurrentUser"]

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    # Only the gateway knows this secret; never trust identity headers on their own.
    gateway_key = request.headers.get("x-gateway-key", "")
    if gateway_key and secrets.compare_digest(
        gateway_key.encode("utf-8"), settings.gateway_secret.get_secret_value().encode("utf-8")
    ):
        try:
            user_id = UUID(request.headers["x-user-id"])
            role = request.headers["x-user-role"]
            if role not in {"customer", "admin"}:
                raise ValueError("Invalid role")
            return CurrentUser(id=user_id, role=role)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid gateway identity") from exc
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="Access token required", headers={"WWW-Authenticate": "Bearer"}
        )
    # Direct calls remain authenticated, including the direct-service benchmark.
    return verify_access_token(credentials.credentials)


def get_page_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token: str | None = Cookie(default=None),
) -> CurrentUser:
    if credentials is None and access_token:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    return get_current_user(request, credentials)
