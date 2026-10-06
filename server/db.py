"""
Database connection pool management using psycopg 3.
Provides separate pools for twin_reader (SELECT only) and twin_writer (INSERT/UPDATE).
"""

import os
from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

READER_DSN = os.getenv("READER_DSN", "postgresql://twin_reader:reader_password@localhost:5432/twin")
WRITER_DSN = os.getenv("WRITER_DSN", "postgresql://twin_writer:writer_password@localhost:5432/twin")
ADMIN_DSN = os.getenv("ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/twin")


@contextmanager
def get_reader_connection() -> Generator[psycopg.Connection, None, None]:
    """Provides a connection from the read-only pool (twin_reader)."""
    with psycopg.connect(READER_DSN, row_factory=dict_row) as conn:
        yield conn


@contextmanager
def get_writer_connection() -> Generator[psycopg.Connection, None, None]:
    """Provides a connection from the validated write pool (twin_writer)."""
    with psycopg.connect(WRITER_DSN, row_factory=dict_row) as conn:
        yield conn


@contextmanager
def get_admin_connection() -> Generator[psycopg.Connection, None, None]:
    """Provides an admin connection for harness operations (reset, scoring)."""
    with psycopg.connect(ADMIN_DSN, row_factory=dict_row) as conn:
        yield conn
