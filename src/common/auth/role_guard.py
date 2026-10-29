from fastapi import Depends, HTTPException, status

from .middleware import get_current_user, get_page_user, CurrentUser

__all__ = ["require_role"]


def require_role(*allowed_roles: str, allow_cookie: bool = False):
    auth_dependency = get_page_user if allow_cookie else get_current_user

    def role_checker(current_user: CurrentUser = Depends(auth_dependency)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yêu cầu quyền: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker
