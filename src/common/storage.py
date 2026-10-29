from datetime import timedelta
from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException
from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout
from urllib3.exceptions import HTTPError

from src.common.config import settings

AVATAR_URL_TTL = 300


class AvatarStorage:
    def __init__(self):
        credentials = {
            "access_key": settings.minio_access_key,
            "secret_key": settings.minio_secret_key.get_secret_value(),
            "secure": settings.minio_secure,
            "region": settings.minio_region,
        }
        self.internal = Minio(
            settings.minio_endpoint, **credentials,
            http_client=PoolManager(timeout=Timeout(connect=3, read=5), retries=1),
        )
        # Sign with the address the uploader can actually reach. Replacing the
        # hostname after signing would invalidate the signature.
        self.public = Minio(settings.minio_public_endpoint, **credentials)

    def ensure_bucket(self):
        if not self.internal.bucket_exists(settings.minio_bucket):
            try:
                self.internal.make_bucket(settings.minio_bucket, location=settings.minio_region)
            except S3Error as exc:
                if exc.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise

    def upload_url(self, user_id: UUID, content_type: str) -> dict:
        object_key = f"avatars/{user_id}/avatar"
        try:
            self.ensure_bucket()
            url = self.public.presigned_put_object(
                settings.minio_bucket, object_key, expires=timedelta(seconds=AVATAR_URL_TTL)
            )
        except (S3Error, HTTPError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Avatar storage unavailable") from exc
        return {
            "upload_url": url,
            "method": "PUT",
            "object_key": object_key,
            "expires_in": AVATAR_URL_TTL,
            "headers": {"Content-Type": content_type},
        }

    def download_url(self, user_id: UUID) -> dict:
        object_key = f"avatars/{user_id}/avatar"
        try:
            self.internal.stat_object(settings.minio_bucket, object_key)
            url = self.public.presigned_get_object(
                settings.minio_bucket, object_key, expires=timedelta(seconds=AVATAR_URL_TTL)
            )
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise HTTPException(status_code=404, detail="Avatar not uploaded") from exc
            raise HTTPException(status_code=503, detail="Avatar storage unavailable") from exc
        except (HTTPError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Avatar storage unavailable") from exc
        return {"download_url": url, "expires_in": AVATAR_URL_TTL}


@lru_cache
def get_avatar_storage() -> AvatarStorage:
    return AvatarStorage()
