from django.core.management.base import BaseCommand
from voting.models import CandidateQuestion

class Command(BaseCommand):
    help = 'Seed candidate questionnaire questions'

    def handle(self, *args, **options):
        questions = [
            "Do you have any outstanding fee balance? (Upload fee statement)",
            "Have you ever been found guilty of academic malpractice?",
            "Do you have any pending disciplinary cases?",
            "Do you have any missing marks?",
            "Have you ever taken a supplementary exam?",
            "Upload your party nomination certificate (PDF) - only for presidential candidates",
            "Upload your fee clearance statement (PDF)",
        ]

        for q in questions:
            obj, created = CandidateQuestion.objects.get_or_create(
                question_text=q,
                defaults={'question_type': 'text' if 'Upload' not in q else 'file'}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created: {q}'))
            else:
                self.stdout.write(self.style.WARNING(f'Already exists: {q}'))