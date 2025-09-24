"""
Celery configuration for Collections Agent.

This module configures Celery for background task processing.
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collections_agent.settings')

app = Celery('collections_agent')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    'cleanup-old-data': {
        'task': 'invoice_collections.tasks.cleanup_old_data_task',
        'schedule': 86400.0,  # Run daily
    },
    'retry-failed-payments': {
        'task': 'invoice_collections.tasks.retry_failed_payments_task',
        'schedule': 3600.0,  # Run hourly
    },
}

app.conf.timezone = 'UTC'


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
