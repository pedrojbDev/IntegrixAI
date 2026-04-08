from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import Base
from app.models import call_event, ops_sync_state, vapi_call_cost  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
