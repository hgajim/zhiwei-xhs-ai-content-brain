"""数据库连接池与事务辅助函数。"""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_pool_lock = Lock()


def _get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(
                conninfo=settings.database_url,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row},
                open=False,
            )
        return _pool


def open_pool() -> None:
    connection_pool = _get_pool()
    if connection_pool.closed:
        connection_pool.open(wait=True)


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def transaction() -> Iterator[Connection]:
    """返回自动提交或回滚的数据库事务。"""
    with _get_pool().connection() as conn:
        with conn.transaction():
            yield conn
