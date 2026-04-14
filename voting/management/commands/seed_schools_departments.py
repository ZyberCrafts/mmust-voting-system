from django.core.management.base import BaseCommand
from voting.models import School, Department

class Command(BaseCommand):
    help = 'Seed schools and departments for registration'

    def handle(self, *args, **options):
        # Schools
        sci, _ = School.objects.get_or_create(name='School of Computing and Informatics', code='SCI')
        sedu, _ = School.objects.get_or_create(name='School of Education', code='SEDU')

        # Departments for SCI
        sci_depts = ['IT', 'ETS', 'Computer Science', 'SIK']
        for dept in sci_depts:
            Department.objects.get_or_create(school=sci, name=dept)

        # Departments for SEDU
        sedu_depts = ['Biology and Chemistry', 'Mathematics and Physics', 'Computer and Biology', 'English and Literature']
        for dept in sedu_depts:
            Department.objects.get_or_create(school=sedu, name=dept)

        self.stdout.write(self.style.SUCCESS('Schools and departments seeded successfully.'))