import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmust_voting.settings')

app = Celery('mmust_voting')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Optional: configure task routing
app.conf.task_routes = {
    'voting.tasks.send_notification_task': {'queue': 'notifications'},
    'voting.tasks.tally_election_results': {'queue': 'tally'},
}

# Optional: configure periodic tasks (Celery Beat)
app.conf.beat_schedule = {
    'cleanup-expired-sessions': {
        'task': 'voting.tasks.cleanup_expired_sessions',
        'schedule': crontab(hour=3, minute=0),  # daily at 3am
    },
    'send-voting-reminders': {
        'task': 'voting.tasks.send_voting_reminders',
        'schedule': crontab(hour=9, minute=0),  # daily at 9am
    },
    'auto-verify-pending-users': {
        'task': 'voting.tasks.auto_verify_pending_users',
        'schedule': crontab(hour=2, minute=30),  # daily at 2:30am
    },
}

# Optional: configure result backend (if used)
app.conf.result_expires = 3600  # 1 hour

# For Celery 5+ you may need this to avoid connection issues on startup
app.conf.broker_connection_retry_on_startup = True

# Optional: task time limits
app.conf.task_time_limit = 30 * 60   # 30 minutes max
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes soft limit

@app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f'Request: {self.request!r}')