from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from api.core.database import Base # importing this registers every model on Base.metadata
from api.models.chunk import Chunk
from api.models.document import Document
from api.models.document_version import DocumentVersion
from api.models.ingestion_job import IngestionJob
from api.models.organization import Organization
from api.models.user import User
from api.models.workspace import Workspace
from api.models.workspace_member import WorkspaceMember

from api.core.config import config as app_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # Single source of truth: the same DATABASE_URL the app uses.
    return app_config.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Make sure pgvector is enabled before any migration touches vector columns.
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()