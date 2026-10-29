from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def database_lifespan(app: FastAPI, url: str, tables: list):
    engine = create_async_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables)
            )
        yield
    finally:
        await engine.dispose()


async def get_db(request: Request):
    async with request.app.state.session_factory() as session:
        yield session
