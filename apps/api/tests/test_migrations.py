import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from conftest import alembic_cfg, sync_url


@pytest.fixture
def scratch_db(monkeypatch):
    """A throwaway database so migrations can be dropped and replayed freely."""
    admin = create_engine(make_url(sync_url()).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS sift_migrations"))
        c.execute(text("CREATE DATABASE sift_migrations"))
    url = make_url(os.environ["DATABASE_URL"]).set(database="sift_migrations")
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    eng = create_engine(sync_url(url.render_as_string(hide_password=False)))
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS sift_migrations"))
    admin.dispose()


def test_migrations_match_the_models(scratch_db):
    from app.db import Base

    command.upgrade(alembic_cfg(), "head")
    with scratch_db.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == []


def test_downgrade_and_upgrade_again(scratch_db):
    cfg = alembic_cfg()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert set(inspect(scratch_db).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    assert {"users", "notes", "items", "google_accounts"} <= set(inspect(scratch_db).get_table_names())
