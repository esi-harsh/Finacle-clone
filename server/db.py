"""
Database connection management using psycopg 3 (PostgreSQL) and sqlite3 (Local fallback).
Allows 100% offline startup without Docker, and connects to Supabase/PostgreSQL when available.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any
from dotenv import load_dotenv

load_dotenv()

DEFAULT_URL = os.getenv("SUPABASE_URL") or os.getenv("DATABASE_URL")
READER_DSN = os.getenv("READER_DSN") or DEFAULT_URL or "postgresql://twin_reader:reader_password@localhost:5432/twin"
WRITER_DSN = os.getenv("WRITER_DSN") or DEFAULT_URL or "postgresql://twin_writer:writer_password@localhost:5432/twin"
ADMIN_DSN = os.getenv("ADMIN_DSN") or DEFAULT_URL or "postgresql://postgres:postgres@localhost:5432/twin"
LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", "finance_twin.db")


class SQLiteDictCursor:
    """Wrapper around sqlite3.Cursor to provide dict-like rows and PostgreSQL %s parameter translation."""
    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor

    def execute(self, sql: str, params: Any = None):
        # Convert PostgreSQL syntax (finance.table -> table, %s -> ?, gen_random_uuid() -> hex)
        cleaned_sql = sql.replace("finance.", "").replace("sap_compat.", "")
        cleaned_sql = cleaned_sql.replace("%s", "?")
        if params is not None:
            if isinstance(params, list):
                params = tuple(params)
            return self.cursor.execute(cleaned_sql, params)
        return self.cursor.execute(cleaned_sql)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [col[0] for col in self.cursor.description]
        return dict(zip(columns, row))

    def fetchall(self):
        rows = self.cursor.fetchall()
        if not rows:
            return []
        columns = [col[0] for col in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class SQLiteConnectionWrapper:
    """Wrapper around sqlite3.Connection to provide cursor context manager compatible with psycopg3."""
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @contextmanager
    def cursor(self):
        cur = self.conn.cursor()
        try:
            yield SQLiteDictCursor(cur)
        finally:
            cur.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.close()


@contextmanager
def get_reader_connection() -> Generator[Any, None, None]:
    """Provides a read-only connection, falling back to local SQLite if PostgreSQL is unreachable."""
    try:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(READER_DSN, row_factory=dict_row, connect_timeout=1)
        try:
            yield conn
        finally:
            conn.close()
    except Exception:
        # Fallback to local SQLite database
        conn = sqlite3.connect(LOCAL_DB_PATH)
        try:
            yield SQLiteConnectionWrapper(conn)
        finally:
            conn.close()


@contextmanager
def get_writer_connection() -> Generator[Any, None, None]:
    """Provides a validated write connection, falling back to local SQLite if PostgreSQL is unreachable."""
    try:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(WRITER_DSN, row_factory=dict_row, connect_timeout=1)
        try:
            yield conn
        finally:
            conn.close()
    except Exception:
        # Fallback to local SQLite database
        conn = sqlite3.connect(LOCAL_DB_PATH)
        try:
            yield SQLiteConnectionWrapper(conn)
        finally:
            conn.close()


@contextmanager
def get_admin_connection() -> Generator[Any, None, None]:
    """Provides an admin connection, falling back to local SQLite if PostgreSQL is unreachable."""
    try:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(ADMIN_DSN, row_factory=dict_row, connect_timeout=1)
        try:
            yield conn
        finally:
            conn.close()
    except Exception:
        # Fallback to local SQLite database
        conn = sqlite3.connect(LOCAL_DB_PATH)
        try:
            yield SQLiteConnectionWrapper(conn)
        finally:
            conn.close()
