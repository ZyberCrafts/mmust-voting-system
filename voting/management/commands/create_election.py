# voting/management/commands/create_election.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from voting.models import Election

class Command(BaseCommand):
    help = 'Create a new election'

    def add_arguments(self, parser):
        parser.add_argument('name', type=str, help='Election name')
        parser.add_argument('--start', type=str, help='Start datetime (YYYY-MM-DD HH:MM:SS)', default=None)
        parser.add_argument('--end', type=str, help='End datetime (YYYY-MM-DD HH:MM:SS)', default=None)
        parser.add_argument('--days', type=int, help='Duration in days (if no end given)', default=1)

    def handle(self, *args, **options):
        name = options['name']
        start_str = options['start']
        end_str = options['end']
        days = options['days']

        now = timezone.now()
        if start_str:
            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            start = timezone.make_aware(start)
        else:
            start = now

        if end_str:
            end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
            end = timezone.make_aware(end)
        else:
            end = start + timedelta(days=days)

        election = Election.objects.create(
            name=name,
            start_time=start,
            end_time=end,
            is_active=True
        )
        self.stdout.write(self.style.SUCCESS(f'Election "{name}" created with ID {election.id}'))