"""Gunicorn settings module: ``gunicorn -c python:py_common.web.gunicorn ...``."""

from py_common.metrics import child_exit

__all__ = ["child_exit"]
