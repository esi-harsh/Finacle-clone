import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, Optional
from dotenv import load_dotenv

load_dotenv()


import urllib.parse


def _clean_dsn(dsn_or_url: Optional[str]) -> Optional[str]:
    if not dsn_or_url:
        return None
    url = dsn_or_url.strip()
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        return None
    if "@" in url:
        prefix, rest = url.split("://", 1)
        userinfo, hostinfo = rest.rsplit("@", 1)
        if ":" in userinfo:
            user, password = userinfo.split(":", 1)
            encoded_password = urllib.parse.quote(password)
            return f"{prefix}://{user}:{encoded_password}@{hostinfo}"
    return url


db_env_url = os.getenv("DATABASE_URL")
if not db_env_url:
    supa = os.getenv("SUPABASE_URL", "")
    if supa.startswith("postgres"):
        db_env_url = supa

DEFAULT_URL = _clean_dsn(db_env_url)

READER_DSN = _clean_dsn(os.getenv("READER_DSN")) or DEFAULT_URL
WRITER_DSN = _clean_dsn(os.getenv("WRITER_DSN")) or DEFAULT_URL
ADMIN_DSN = _clean_dsn(os.getenv("ADMIN_DSN")) or DEFAULT_URL
LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", "finance_twin.db")


class SQLiteDictCursor:
    """Wrapper around sqlite3.Cursor to provide dict-like rows and PostgreSQL syntax translation."""
    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor

    def execute(self, sql: str, params: Any = None):
        # Convert PostgreSQL syntax (finance.table -> table, %s -> ?, ILIKE -> LIKE, typecasts)
        cleaned_sql = sql.replace("finance.", "").replace("sap_compat.", "")
        cleaned_sql = re.sub(r'\bILIKE\b', 'LIKE', cleaned_sql, flags=re.IGNORECASE)
        cleaned_sql = re.sub(r'::[a-zA-Z0-9_]+', '', cleaned_sql)
        cleaned_sql = re.sub(r'EXTRACT\s*\(\s*DOW\s+FROM\s+([a-zA-Z0-9_]+)\s*\)', r"CAST(strftime('%w', \1) AS INTEGER)", cleaned_sql, flags=re.IGNORECASE)
        cleaned_sql = cleaned_sql.replace("%s", "?")

        if params is not None:
            if isinstance(params, list):
                params = tuple(params)
            elif not isinstance(params, (tuple, dict)):
                params = (params,)
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
        # Register custom SQLite functions for PostgreSQL compatibility
        try:
            self.conn.create_function("MOD", 2, lambda a, b: (float(a) % float(b)) if a is not None and b is not None else None)
        except Exception:
            pass

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


def _get_sqlite_conn() -> SQLiteConnectionWrapper:
    conn = sqlite3.connect(LOCAL_DB_PATH)
    return SQLiteConnectionWrapper(conn)


@contextmanager
def get_reader_connection() -> Generator[Any, None, None]:
    """Provides a read-only connection, falling back to local SQLite if PostgreSQL is unreachable."""
    if READER_DSN:
        try:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(READER_DSN, row_factory=dict_row, connect_timeout=2)
            try:
                yield conn
                return
            finally:
                conn.close()
        except Exception:
            pass
    # Fallback to local SQLite database
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_writer_connection() -> Generator[Any, None, None]:
    """Provides a validated write connection, falling back to local SQLite if PostgreSQL is unreachable."""
    if WRITER_DSN:
        try:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(WRITER_DSN, row_factory=dict_row, connect_timeout=2)
            try:
                yield conn
                return
            finally:
                conn.close()
        except Exception:
            pass
    # Fallback to local SQLite database
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_admin_connection() -> Generator[Any, None, None]:
    """Provides an admin connection, falling back to local SQLite if PostgreSQL is unreachable."""
    if ADMIN_DSN:
        try:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(ADMIN_DSN, row_factory=dict_row, connect_timeout=2)
            try:
                yield conn
                return
            finally:
                conn.close()
        except Exception:
            pass
    # Fallback to local SQLite database
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()
