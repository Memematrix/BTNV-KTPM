from src.common.config import settings
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
#expire_on_commit: prevent object attribute expire after commit, i.e. user.id will still exist after db.commit() -> so when return user all the attribure still exist

# the base for sqlalchemy to read the class in models as table
class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
