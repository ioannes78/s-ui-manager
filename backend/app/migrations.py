from sqlalchemy import inspect, text


NODE_COLUMNS = {
    "group_name": "VARCHAR(100) NOT NULL DEFAULT ''",
    "tags": "TEXT NOT NULL DEFAULT '[]'",
    "notes": "TEXT NOT NULL DEFAULT ''",
    "sui_version": "VARCHAR(50) NOT NULL DEFAULT ''",
    "last_latency_ms": "INTEGER",
    "last_checked_at": "TIMESTAMP",
}


def run_compat_migrations(engine) -> None:
    """Small idempotent migration needed before Alembic is introduced.

    V1.x created tables directly with SQLAlchemy. V2 keeps those databases and
    adds the new Node columns before the ORM starts querying the table.
    """
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("nodes")}
    with engine.begin() as connection:
        for name, ddl in NODE_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE nodes ADD COLUMN {name} {ddl}"))
