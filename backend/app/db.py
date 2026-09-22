"""Database setup — SQLAlchemy. Pick the backend with the DB_TYPE flag:
   DB_TYPE=sqlite      -> local file (default, nothing to configure)
   DB_TYPE=postgresql  -> Postgres, credentials from DATABASE_URL or DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
Tables are created automatically in app.main."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_TYPE = os.getenv("DB_TYPE", "sqlite").strip().lower()

if DB_TYPE == "postgresql":
    DATABASE_URL = os.getenv("DATABASE_URL") or (
        f"postgresql+psycopg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )
    connect_args = {}
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./migration.db")
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()