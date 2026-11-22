"""Alembic environment. The DB URL comes from DOCUMIND_DATABASE_URL, never from alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.database.base import Base
import app.models  # noqa: F401  (registers all tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata
SCHEMA = settings.db_schema


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True, version_table_schema=SCHEMA)
    with context.begin_transaction():
        if SCHEMA:
            context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
            context.execute(f"SET search_path TO {SCHEMA}, public")
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool,
                                     connect_args=settings.db_connect_args)
    with connectable.connect() as connection:
        if SCHEMA:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          version_table_schema=SCHEMA)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
