web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn mmust_voting.wsgi:application
worker: celery -A mmust_voting worker -l info