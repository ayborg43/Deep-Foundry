import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("agentarium")
app.config_from_object("django.conf:settings", namespace="CELERY")

# `worker` is a plain package, not a Django app in INSTALLED_APPS, so the
# no-args form of autodiscover_tasks() (which only scans INSTALLED_APPS)
# would silently miss worker/tasks.py — pass it explicitly.
app.autodiscover_tasks(["core", "worker"])
