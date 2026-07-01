"""Alembic environment.

The DB URL comes from application settings (``effective_database_url``, i.e.
``CRAFTON_DATABASE_URL`` with the db-name swapped for ``CRAFTON_DB_NAME`` when set)
so we never duplicate credentials in ``alembic.ini`` and per-PR previews migrate
against their own isolated database. Importing ``app.models`` registers every
table on ``Base.metadata`` for autogeneration.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().effective_database_url)

# Fixed int64 key for the migration advisory lock (see run_migrations_online).
_MIGRATION_LOCK_KEY = 727274

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            # Serialize concurrent migrators (e.g. multiple Cloud Run instances
            # booting the same revision) so they can't corrupt the schema. This
            # MUST be the first statement inside the transaction: running any
            # statement on the connection *before* begin_transaction() makes
            # SQLAlchemy autobegin a tx that Alembic then won't commit, so DDL
            # silently rolls back on a fresh DB. pg_advisory_xact_lock is
            # transaction-scoped (auto-released on commit) and per-database, so
            # prod and each per-PR database lock independently.
            connection.exec_driver_sql(
                f"SELECT pg_advisory_xact_lock({_MIGRATION_LOCK_KEY})"
            )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
