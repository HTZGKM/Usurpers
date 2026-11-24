from datetime import date, datetime
from decimal import Decimal

import psycopg


class ResultRow(dict):
    """Keep the named and positional access that SQLite rows expose to services."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _api_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_factory(cursor):
    columns = tuple(column.name for column in cursor.description or ())

    def make_row(values):
        return ResultRow(zip(columns, map(_api_value, values)))

    return make_row


class PostgresConnection(psycopg.Connection):
    def execute(self, query, params=None, **kwargs):
        # Service queries use qmark placeholders, without question marks in SQL literals.
        if isinstance(query, str):
            query = query.replace("?", "%s").replace(
                "CURRENT_TIMESTAMP", "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"
            )
        return super().execute(query, params, **kwargs)

    def executemany(self, query, params):
        with self.cursor() as cursor:
            cursor.executemany(query.replace("?", "%s"), params)


def connect(url):
    # Disabling prepared statements also supports pooled Neon connections.
    return PostgresConnection.connect(
        url, row_factory=_row_factory, prepare_threshold=None, connect_timeout=8
    )
