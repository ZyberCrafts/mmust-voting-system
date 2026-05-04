import random
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
from voting.models import (
    User, School, Department, Position, Party, Election,
    Candidate, VoterStatus, PollingOfficerTest
)

class Command(BaseCommand):
    help = 'Generate dummy data for testing (gender-aware candidates)'

    def handle(self, *args, **options):
        self.stdout.write("Generating dummy data...")

        # 1. School of Computing
        school, _ = School.objects.get_or_create(name="School of Computing and Informatics", code="SCI")
        dept, _ = Department.objects.get_or_create(school=school, name="Computer Science")

        # 2. Parties
        parties = []
        for name, abbr, color in [("Progressive Alliance", "PA", "#FF5733"),
                                   ("Unity Front", "UF", "#33FF57"),
                                   ("Innovation Party", "IP", "#3357FF")]:
            p, _ = Party.objects.get_or_create(name=name, abbreviation=abbr, defaults={'color': color})
            parties.append(p)

        # 3. Positions (keep all 10)
        pos_list = [
            "President (Party Ticket)",
            "School Representative (Male)",
            "School Representative (Female)",
            "Hall 1 Representative (Male)",
            "Hall 2 Representative (Male)",
            "Hall 3 Representative (Female)",
            "Hall 4 Representative (Female)",
            "Hall 4 Representative (Male)",
            "Non-resident Representative (Male)",
            "Non-resident Representative (Female)"
        ]
        positions = {}
        for name in pos_list:
            p, _ = Position.objects.get_or_create(name=name, school=school, department=None)
            positions[name] = p

        # 4. Create Election (active for 7 days)
        now = timezone.now()
        election, _ = Election.objects.get_or_create(
            name="Student Leadership Elections 2025",
            defaults={
                'start_time': now,
                'end_time': now + timedelta(days=7),
                'is_active': True
            }
        )

        # 5. Create 100 Auto‑approved Voters (students)
        for i in range(1, 101):
            adm = f"COM/B/01-{i:03d}/2022"
            user, created = User.objects.get_or_create(
                username=f"student{i}",
                defaults={
                    'first_name': f"Student{i}",
                    'last_name': "Voter",
                    'email': f"student{i}@demo.mmust.ac.ke",  # fake domain, no bounce
                    'phone': f"+254712345{i:03d}",
                    'role': 'voter',
                    'admission_number': adm,
                    'course': 'Computer Science',
                    'year_of_study': random.randint(1, 4),
                    'school': school,
                    'department': dept,
                    'residence': 'Main Campus',
                    'security_question': 'mother_maiden',
                    'security_answer': 'smith',
                    'id_type': 'national_id',
                    'is_verified': True,
                    'password': make_password('testpass123')
                }
            )
            if created:
                self.stdout.write(f"Created voter: {user.username}")

        # 6. Helper to create a candidate
        def create_candidate(username, first_name, last_name, email, position_name, party=None, gender=None, verified=True):
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone': f"+254712345{random.randint(500,999)}",
                    'role': 'candidate',
                    'admission_number': f"COM/B/01-{random.randint(200,300):03d}/2022",  # not auto-verified
                    'course': 'Computer Science',
                    'year_of_study': 4,
                    'school': school,
                    'department': dept,
                    'residence': 'Main Campus',
                    'security_question': 'mother_maiden',
                    'security_answer': 'smith',
                    'id_type': 'national_id',
                    'is_verified': True,  # they will be verified manually? we set True for demo
                    'password': make_password('testpass123')
                }
            )
            Candidate.objects.get_or_create(
                user=user, election=election, position=positions[position_name],
                defaults={
                    'party': party,
                    'verified': verified,
                    'manifesto': f"I am {first_name} {last_name} and I will serve you well.",
                    'candidate_metadata': {'gender': gender} if gender else {}
                }
            )
            self.stdout.write(f"Created candidate: {first_name} {last_name} for {position_name}")

        # 7. Presidential candidates (one per party)
        for i, party in enumerate(parties):
            create_candidate(
                username=f"pres_{party.abbreviation.lower()}",
                first_name=f"Pres{i+1}",
                last_name=party.name,
                email=f"pres{i+1}@demo.mmust.ac.ke",
                position_name="President (Party Ticket)",
                party=party,
                gender='male'   # irrelevant for president
            )

        # 8. School Representatives (Male & Female)
        create_candidate("school_rep_male", "John", "MaleRep", "male.rep@demo.mmust.ac.ke",
                         "School Representative (Male)", gender='male')
        create_candidate("school_rep_female", "Jane", "FemaleRep", "female.rep@demo.mmust.ac.ke",
                         "School Representative (Female)", gender='female')

        # 9. Hall Representatives (only male for Hall1, Hall2, Hall4Male; only female for Hall3, Hall4Female)
        hall_candidates = [
            ("Hall 1 Representative (Male)", "hall1_male", "Mike", "Hall1Male", "hall1@demo.mmust.ac.ke", 'male'),
            ("Hall 2 Representative (Male)", "hall2_male", "James", "Hall2Male", "hall2@demo.mmust.ac.ke", 'male'),
            ("Hall 3 Representative (Female)", "hall3_female", "Sarah", "Hall3Female", "hall3@demo.mmust.ac.ke", 'female'),
            ("Hall 4 Representative (Female)", "hall4_female", "Linda", "Hall4Female", "hall4f@demo.mmust.ac.ke", 'female'),
            ("Hall 4 Representative (Male)", "hall4_male", "David", "Hall4Male", "hall4m@demo.mmust.ac.ke", 'male')
        ]
        for pos_name, username, first, last, email, gender in hall_candidates:
            create_candidate(username, first, last, email, pos_name, gender=gender)

        # 10. Non-resident Representatives (Male & Female)
        create_candidate("nonres_male", "Peter", "NonResMale", "nonres.m@demo.mmust.ac.ke",
                         "Non-resident Representative (Male)", gender='male')
        create_candidate("nonres_female", "Grace", "NonResFemale", "nonres.f@demo.mmust.ac.ke",
                         "Non-resident Representative (Female)", gender='female')

        # 11. Admin user
        User.objects.get_or_create(
            username='admin', is_superuser=True, is_staff=True,
            defaults={
                'first_name': 'Admin', 'last_name': 'User', 'email': 'admin@demo.mmust.ac.ke',
                'phone': '+254712345000', 'password': make_password('admin123'),
                'role': 'admin', 'is_verified': True
            }
        )

        # 12. Polling Officers (2)
        for i in [1,2]:
            user, _ = User.objects.get_or_create(
                username=f"officer{i}",
                defaults={
                    'first_name': f"Officer{i}", 'last_name': "Polling",
                    'email': f"officer{i}@demo.mmust.ac.ke",
                    'phone': f"+254712345{700+i}",
                    'role': 'polling_officer',
                    'staff_id': f"STAFF00{i}",
                    'department_work': 'ICT',
                    'password': make_password('testpass123'),
                    'is_verified': True
                }
            )
            PollingOfficerTest.objects.get_or_create(
                user=user, defaults={'score': 85, 'passed': True, 'answers': {'q1':'good'}}
            )

        self.stdout.write(self.style.SUCCESS("Dummy data generation complete! All positions have appropriate gender-specific candidates."))