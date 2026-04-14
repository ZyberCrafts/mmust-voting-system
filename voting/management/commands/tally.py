# voting/management/commands/tally.py

from django.core.management.base import BaseCommand
from voting.models import Election
from voting.tasks import tally_election_results

class Command(BaseCommand):
    help = 'Tally results for an election'

    def add_arguments(self, parser):
        parser.add_argument('election_id', type=int, help='Election ID')

    def handle(self, *args, **options):
        election_id = options['election_id']
        try:
            election = Election.objects.get(id=election_id)
            if not election.is_closed():
                self.stdout.write(self.style.WARNING('Election is not closed yet.'))
                return
            result = tally_election_results(election_id)
            if result:
                self.stdout.write(self.style.SUCCESS(f'Tally completed for election {election_id}'))
            else:
                self.stdout.write(self.style.ERROR('Tally failed.'))
        except Election.DoesNotExist:
            self.stdout.write(self.style.ERROR('Election not found.'))