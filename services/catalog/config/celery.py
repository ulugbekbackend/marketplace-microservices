"""Celery application: image processing and the stale reservation sweep (beat) run here
(compose service catalog-worker, started with --beat)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("catalog")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
