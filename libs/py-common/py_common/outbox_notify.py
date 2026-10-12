"""Wake an outbox relay as soon as a transaction with new outbox rows commits.

A writer runs ``NOTIFY_SQL`` in the transaction that adds outbox rows: Postgres delivers the
notification at commit, drops it on rollback and folds repeats within one transaction into
one. The relay ``LISTEN``s on a connection of its own and waits for a notification instead
of sleeping a fixed interval. The interval stays as the upper bound, so a lost notification
(or a broken listening connection) only delays a batch, it never loses one.
"""

import logging
import time

import psycopg

logger = logging.getLogger(__name__)

CHANNEL = "outbox"
NOTIFY_SQL = f"NOTIFY {CHANNEL}"


class NotifyWaiter:
    """``wait(timeout)`` returns early when the channel is notified.

    The connection is opened lazily and reopened after an error; while it is down
    ``wait`` falls back to a plain sleep.
    """

    def __init__(self, conninfo: str, *, channel: str = CHANNEL) -> None:
        self._conninfo = conninfo
        self._channel = channel
        self._conn: psycopg.Connection[tuple[object, ...]] | None = None

    def _connect(self) -> psycopg.Connection[tuple[object, ...]]:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._conninfo, autocommit=True)
            self._conn.execute(f"LISTEN {self._channel}")
        return self._conn

    def wait(self, timeout: float) -> bool:
        """True when a notification arrived within ``timeout`` seconds."""
        try:
            conn = self._connect()
            woken = any(True for _ in conn.notifies(timeout=timeout, stop_after=1))
            if woken:
                # Several commits may have notified meanwhile: one batch covers them all.
                for _ in conn.notifies(timeout=0):
                    pass
            return woken
        except psycopg.Error:
            logger.warning("outbox listen connection failed", exc_info=True)
            self.close()
            time.sleep(timeout)
            return False

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None and not conn.closed:
            conn.close()


def django_conninfo(alias: str = "default") -> str:
    """Connection string of a Django database, for a listening connection beside the ORM."""
    from django.conf import settings
    from psycopg.conninfo import make_conninfo

    database = settings.DATABASES[alias]
    params = {
        "dbname": database.get("NAME"),
        "user": database.get("USER"),
        "password": database.get("PASSWORD"),
        "host": database.get("HOST"),
        "port": database.get("PORT"),
    }
    return make_conninfo(**{key: str(value) for key, value in params.items() if value})
