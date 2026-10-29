from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.common.config import settings
from src.common.database import database_lifespan
from src.models import User
from src.routers.user import router


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with database_lifespan(app, database_url or settings.database_url, [User.__table__]):
            yield

    app = FastAPI(title="User service", lifespan=lifespan)
    app.include_router(router, prefix="/users", tags=["users"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "users"}

    return app


app = create_app()
