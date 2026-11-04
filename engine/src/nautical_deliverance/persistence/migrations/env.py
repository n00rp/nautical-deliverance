"""Alembic environment: runs as nd_owner via ND_MIGRATION_DATABASE_URL."""

import os

from alembic import context
from sqlalchemy import create_engine

from nautical_deliverance.persistence.models import Base

with create_engine(os.environ["ND_MIGRATION_DATABASE_URL"]).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
