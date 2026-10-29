from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.common.auth.hash_pw import hash_password, verify_password
from src.common.auth.jwt import create_access_token
from src.common.auth.middleware import CurrentUser, get_current_user
from src.common.database import get_db
from src.common.storage import AvatarStorage, get_avatar_storage
from src.models import User
from src.schemas import (
    AvatarDownloadResponse, AvatarUploadRequest, AvatarUploadResponse,
    LoginRequest, RegisterRequest, TokenResponse, UserResponse,
)

router = APIRouter()
Database = Annotated[AsyncSession, Depends(get_db)]
Identity = Annotated[CurrentUser, Depends(get_current_user)]
Storage = Annotated[AvatarStorage, Depends(get_avatar_storage)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: Database):
    user = User(
        username=payload.username,
        password_hash=await run_in_threadpool(hash_password, payload.password),
        name=payload.name,
        phone=payload.phone,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Database):
    user = await db.scalar(select(User).where(User.username == payload.username))
    if user is None or not await run_in_threadpool(verify_password, payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "user": user,
    }


@router.post("/logout", status_code=204)
async def logout(current_user: Identity):
    # JWTs are stateless: clients discard the token; it remains valid until expiry.
    return Response(status_code=204)


@router.get("", response_model=UserResponse)
@router.get("/me", response_model=UserResponse)
async def get_me(db: Database, current_user: Identity):
    user = await db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/me/avatar/upload-url", response_model=AvatarUploadResponse)
async def avatar_upload_url(
    payload: AvatarUploadRequest, db: Database, current_user: Identity, storage: Storage
):
    await get_me(db, current_user)
    return await run_in_threadpool(storage.upload_url, current_user.id, payload.content_type)


@router.get("/me/avatar", response_model=AvatarDownloadResponse)
async def avatar_download_url(db: Database, current_user: Identity, storage: Storage):
    await get_me(db, current_user)
    return await run_in_threadpool(storage.download_url, current_user.id)
