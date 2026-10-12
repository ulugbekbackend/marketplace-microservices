"""Gunicorn settings module: ``gunicorn -c python:py_common.web.gunicorn ...``.

Requests spend most of their time waiting on other services (auth ``/verify``, cart, catalog)
and the database, so each worker serves several requests on threads instead of blocking on
one. The worker count comes from gunicorn's own ``WEB_CONCURRENCY``; anything else can be
changed with ``GUNICORN_CMD_ARGS`` (e.g. ``--threads 8``). Each thread keeps its own database
connection, so workers x threads per service has to fit Postgres ``max_connections``.
"""

from py_common.metrics import child_exit

worker_class = "gthread"
threads = 4
# gunicorn's default line plus the request time in milliseconds.
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(M)sms'

__all__ = ["access_log_format", "child_exit", "threads", "worker_class"]
