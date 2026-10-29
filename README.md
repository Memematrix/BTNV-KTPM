# BTNV-KTPM

## Local setup

1. Install dependencies with `uv sync`.
2. Copy `.env.example` to `.env` and set a private `SECRET_KEY`.

The database uses SQLite through SQLAlchemy's async `aiosqlite` driver. By
default, the first connection creates `btvn_ktpm.db` in the working directory;
no separate database server is needed. Set `DATABASE_URL` in `.env` to change
the file location, for example `sqlite+aiosqlite:///./btvn_ktpm.db`.

SQLite foreign key constraints are enabled for every connection. Existing
PostgreSQL data is not copied automatically.
