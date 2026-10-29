from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.common.config import settings
from src.common.database import database_lifespan
from src.models import Orders
from src.routers.orders import router


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with database_lifespan(
            app, database_url or settings.order_database_url, [Orders.__table__]
        ):
            yield

    app = FastAPI(title="Order service", lifespan=lifespan)
    app.include_router(router, prefix="/orders", tags=["orders"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "orders"}

    return app


app = create_app()
