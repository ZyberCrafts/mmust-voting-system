from django.core.management.base import BaseCommand
from voting.models import User

class Command(BaseCommand):
    help = 'Convert existing security answers to lowercase'

    def handle(self, *args, **options):
        users = User.objects.all()
        updated = 0
        for user in users:
            if user.security_answer:
                lower = user.security_answer.lower()
                if user.security_answer != lower:
                    user.security_answer = lower
                    user.save()
                    updated += 1
        self.stdout.write(self.style.SUCCESS(f'Updated {updated} users.'))