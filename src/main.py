from fastapi.staticfiles import StaticFiles
from src.common.database import engine, Base
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from src.routers import user, orders

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup -> scan all models(Base) and create missing db tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown -> close all connection pools
    await engine.dispose()

app = FastAPI(lifespan=lifespan)


app.include_router(user.router, prefix="/api/auth", tags=["auth"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
