import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Make apps/api importable regardless of cwd (mirrors prepend_sys_path in alembic.ini).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import get_settings  # noqa: E402
from db import Base  # noqa: E402
import models  # noqa: E402,F401  (import registers all model classes on Base.metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull the DB URL from the same Settings all the app code uses, rather than
# duplicating it in alembic.ini. DATABASE_URL env var overrides this at
# migration-run time (see the sqlite smoke test in apps/api/tests for an
# example of overriding it for a throwaway DB).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
