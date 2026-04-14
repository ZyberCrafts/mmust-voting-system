from django.core.management.base import BaseCommand
from django.utils import timezone
from accountability.models import RatingSession
from voting.models import Election, Candidate

class Command(BaseCommand):
    help = 'Create a rating session for a completed election'

    def add_arguments(self, parser):
        parser.add_argument('election_id', type=int)
        parser.add_argument('--days', type=int, default=30, help='Rating period length in days')

    def handle(self, *args, **options):
        election = Election.objects.get(id=options['election_id'])
        if not election.is_closed():
            self.stdout.write(self.style.ERROR('Election not closed yet'))
            return
        # Mark winners (you may need to set winners manually or via algorithm)
        # For now, assume winners are already marked via admin.
        start = timezone.now()
        end = start + timezone.timedelta(days=options['days'])
        session = RatingSession.objects.create(election=election, start_date=start, end_date=end)
        self.stdout.write(self.style.SUCCESS(f'Rating session created for {election.name} (ID {session.id})'))