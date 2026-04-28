"""
tase-intel — Alembic environment configuration.

Batch 2: migration runner only. No models, no schema definitions.
Loads DATABASE_URL from .env via python-dotenv.
"""

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Load .env from project root (python-dotenv resolves ${VAR} interpolation)
load_dotenv()

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read DATABASE_URL from environment; fall back to constructing from parts.
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    user = os.environ.get("POSTGRES_USER", "tase_intel")
    password = os.environ.get("POSTGRES_PASSWORD", "changeme")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "tase_intel")
    database_url = (
        f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
    )

config.set_main_option("sqlalchemy.url", database_url)

# No target_metadata — V1 uses hand-written SQL migrations, not autogenerate.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
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
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
