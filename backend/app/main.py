"""A360 → Power Automate Migration Studio — API.
Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .db import Base, engine, DB_TYPE, DATABASE_URL
from . import models  # noqa: F401  (registers tables)
from .routers import projects, config

Base.metadata.create_all(bind=engine)

# Lightweight upgrade for databases created by an earlier version (new tables are created above;
# new columns on existing tables are added here). Use Alembic if the schema grows further.
from sqlalchemy import inspect, text
with engine.begin() as conn:
    cols = {c["name"] for c in inspect(conn).get_columns("bots")}
    if "classify_source" not in cols:
        conn.execute(text("ALTER TABLE bots ADD COLUMN classify_source VARCHAR(200)"))

app = FastAPI(title="A360 Migration Studio API", version="1.0.0")
app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router)
app.include_router(config.router)


@app.get("/api/health")
def health():
    from urllib.parse import urlsplit
    u = urlsplit(DATABASE_URL)
    out = DATABASE_URL
    if u.password:
        out = u._replace(netloc=f"{u.username}:••••@{u.hostname}"
                         + (f":{u.port}" if u.port else "")).geturl()
    return {"status": "ok", "database": DB_TYPE, "database_url": out}
