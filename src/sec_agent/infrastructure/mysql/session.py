from __future__ import annotations

from sqlalchemy import Engine, create_engine, inspect, text
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
    ensure_existing_schema(engine)


def ensure_existing_schema(engine: Engine) -> None:
    """给已存在的旧表补齐新增列，保证部署后可自动升级最小表结构。"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing_columns = [column for column in table.columns if column.name not in existing_columns]
        if not missing_columns:
            continue
        with engine.begin() as connection:
            for column in missing_columns:
                column_type = column.type.compile(dialect=engine.dialect)
                nullable = "" if column.nullable else " NOT NULL"
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}{nullable}"))


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
