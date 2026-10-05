"""Celery application: the scheduled expiry of overdue orders (compose service order-worker)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("order")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
