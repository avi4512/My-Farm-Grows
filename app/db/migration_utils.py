"""Helpers that make Alembic migrations safe to re-run.

Databases created before the migration history was repaired may already
contain some tables (they were created by Base.metadata.create_all()).
These helpers let a migration create only what is missing.

In offline (--sql) mode no database is inspected, so every object is
treated as missing and the full DDL is emitted.
"""

import sqlalchemy as sa

from alembic import context, op


def _inspector():
    return sa.inspect(op.get_bind())


def has_table(table_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return _inspector().has_table(table_name)


def has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode() or not has_table(table_name):
        return False
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    unique: bool = False,
) -> None:
    if not has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def column_type(table_name: str, column_name: str):
    """Return the reflected type of a column, or None if it is absent."""
    if context.is_offline_mode() or not has_table(table_name):
        return None
    for column in _inspector().get_columns(table_name):
        if column["name"] == column_name:
            return column["type"]
    return None


def drop_table_if_exists(table_name: str) -> None:
    if context.is_offline_mode() or has_table(table_name):
        op.drop_table(table_name)
