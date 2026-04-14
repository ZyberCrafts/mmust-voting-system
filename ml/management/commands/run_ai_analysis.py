from django.core.management.base import BaseCommand
from ml.tasks import analyze_all_manifestos, analyze_all_feedback

class Command(BaseCommand):
    help = "Run all AI analysis tasks (manifesto, feedback, etc.)"

    def handle(self, *args, **options):
        self.stdout.write("Analyzing manifestos...")
        analyze_all_manifestos()
        self.stdout.write("Analyzing feedback...")
        analyze_all_feedback()
        self.stdout.write("Done.")