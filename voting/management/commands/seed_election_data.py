from django.core.management.base import BaseCommand
from voting.models import Position, Party, CandidateQuestion

class Command(BaseCommand):
    help = 'Seed MMUST election positions and questionnaire questions'

    def handle(self, *args, **options):
        # Positions
        positions = [
            "President (Party Ticket)",
            "School Representative (Male)",
            "School Representative (Female)",
            "Hall 1 Representative (Male)",
            "Hall 2 Representative (Male)",
            "Hall 3 Representative (Female)",
            "Hall 4 Representative (Female)",
            "Hall 4 Representative (Male)",
            "Non-resident Representative (Male)",
            "Non-resident Representative (Female)",
        ]
        for pos in positions:
            Position.objects.get_or_create(name=pos)

        # Questionnaire questions
        questions = [
            "Do you have any outstanding fee balance?",
            "Have you ever been found guilty of academic malpractice?",
            "Do you have any pending disciplinary cases?",
            "Upload your party nomination certificate (PDF)",
            "Upload your fee clearance statement",
            "Explain your vision for the position",
        ]
        for q in questions:
            CandidateQuestion.objects.get_or_create(question_text=q)

        self.stdout.write(self.style.SUCCESS("Election data seeded."))