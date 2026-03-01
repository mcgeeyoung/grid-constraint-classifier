"""Shared test fixtures for grid-constraint-classifier tests.

Sets up an in-memory SQLite database with all tables (Geometry columns
replaced with String, autoincrement on composite PKs removed for SQLite
compatibility). Provides a FastAPI TestClient with the DB dependency
overridden.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Override DATABASE_URL before any app imports
os.environ["DATABASE_URL"] = "sqlite://"
# Point Redis to a non-existent port so caching is disabled during tests
os.environ["REDIS_URL"] = "redis://localhost:16379/0"

import pandas as pd
from sqlalchemy import create_engine, String, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Create the test engine with StaticPool so the same in-memory DB is shared
# across threads (TestClient runs async handlers in a separate thread).
_engine = create_engine(
    "sqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def _patched_create_engine(url, **kwargs):
    """Return the test SQLite engine regardless of args."""
    return _engine


# Apply patch before importing app modules
_ce_patch = patch("sqlalchemy.create_engine", side_effect=_patched_create_engine)
_ce_patch.start()

# Force re-import of app.database with our patched create_engine
if "app.database" in sys.modules:
    del sys.modules["app.database"]

import app.database  # noqa: E402
app.database.engine = _engine
app.database.SessionLocal = _TestSession

# Patch register_spatial_sync to be a no-op (requires PostGIS at runtime)
with patch("app.spatial_sync.register_spatial_sync", lambda: None):
    from app.main import app  # noqa: E402

from app.database import get_db  # noqa: E402
from app.models.base import Base  # noqa: E402

# Stop the create_engine patch
_ce_patch.stop()


def _fix_sqlite_compat():
    """Fix SQLite incompatibilities in model metadata.

    1. Replace geoalchemy2 Geometry/Geography columns with String.
    2. Remove autoincrement on composite primary keys (SQLite limitation).
    """
    try:
        from geoalchemy2 import Geometry, Geography
        geo_types = (Geometry, Geography)
    except ImportError:
        geo_types = ()

    for table in Base.metadata.sorted_tables:
        if geo_types:
            for col in table.columns:
                if isinstance(col.type, geo_types):
                    col.type = String()

        pk_cols = [c for c in table.columns if c.primary_key]
        if len(pk_cols) > 1:
            for col in pk_cols:
                if col.autoincrement is True:
                    col.autoincrement = False


_fix_sqlite_compat()
Base.metadata.create_all(bind=_engine)


@pytest.fixture()
def db_session():
    """Provide a DB session for tests. Uses the shared in-memory SQLite DB."""
    session = _TestSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with get_db overridden to use the test session."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ── Sample data fixtures ──

@pytest.fixture()
def hourly_ba_df():
    """8760-hour DataFrame for congestion calculator tests."""
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=8760, freq="h"),
        "demand_mw": 1000.0,
        "net_generation_mw": 700.0,
        "total_interchange_mw": -300.0,
        "net_imports_mw": 300.0,
    })
