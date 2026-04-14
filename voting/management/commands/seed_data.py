# voting/management/commands/seed_data.py

from django.core.management.base import BaseCommand
from voting.models import School, Department, Position, Party

class Command(BaseCommand):
    help = 'Seed initial data: schools, departments, positions, parties'

    def handle(self, *args, **options):
        # Schools
        schools = [
            ('School of Computing and Informatics', 'SCI'),
            ('School of Education', 'SEDU'),
            ('School of Engineering', 'ENG'),
            ('School of Medicine', 'MED'),
            ('School of Business and Economics', 'BUS'),
        ]
        for name, code in schools:
            School.objects.get_or_create(name=name, code=code)

        # Departments (example for SCI)
        sci = School.objects.get(code='SCI')
        depts = ['Computer Science', 'Information Technology', 'Software Engineering', 'Data Science']
        for d in depts:
            Department.objects.get_or_create(school=sci, name=d)

        # Positions
        positions = [
            ('University President', None, None),
            ('Deputy University President', None, None),
            ('School President', sci, None),
            ('Deputy School President', sci, None),
            ('Head of Department', None, Department.objects.filter(school=sci).first()),
            ('Class Representative', None, None),
        ]
        for name, school, dept in positions:
            Position.objects.get_or_create(name=name, school=school, department=dept)

        # Parties
        parties = [
            ('Progressive Alliance', 'PA', '#FF5733'),
            ('Unity Front', 'UF', '#33FF57'),
            ('Innovation Party', 'IP', '#3357FF'),
        ]
        for name, abbr, color in parties:
            Party.objects.get_or_create(name=name, abbreviation=abbr, defaults={'color': color})

        self.stdout.write(self.style.SUCCESS('Seed data loaded successfully.'))