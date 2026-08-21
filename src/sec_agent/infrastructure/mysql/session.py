from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from sec_agent.infrastructure.mysql.models import Base


def create_mysql_engine(dsn: str) -> Engine:
    return create_engine(
        dsn,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

