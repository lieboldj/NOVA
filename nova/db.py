from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from nova.models import Base


def make_engine(url: str):
    if url.startswith("sqlite"):
        Path(".data").mkdir(exist_ok=True)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        **({"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}),
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_setup(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")

    return engine


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)


def initialize(engine):
    Base.metadata.create_all(engine)
