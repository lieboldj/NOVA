from alembic import context

from nova.config import get_settings
from nova.db import make_engine
from nova.models import Base


def run():
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
