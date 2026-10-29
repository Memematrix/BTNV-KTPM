from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt as pyjwt

from .jwt import verify_access_token, TokenPayload as CurrentUser  # re-export cho dễ đọc ở nơi dùng

__all__ = ["get_current_user", "get_page_user", "CurrentUser"]

# HTTPBearer tự động đọc header: Authorization: Bearer <token>
# auto_error=False để tự kiểm soát response 401 thay vì để FastAPI trả lỗi mặc định.
_bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        current_user = verify_access_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user


def get_page_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    access_token: str | None = Cookie(default=None),
) -> CurrentUser:
    if credentials is None and access_token:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=access_token
        )
    return get_current_user(credentials)
