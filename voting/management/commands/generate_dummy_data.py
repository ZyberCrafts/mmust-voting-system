import random
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
from voting.models import (
    User, School, Department, Position, Party, Election,
    Candidate, PollingOfficerTest
)

class Command(BaseCommand):
    help = 'Generate dummy data with 3 competitors per position'

    def handle(self, *args, **options):
        self.stdout.write("Generating dummy data with multiple competitors...")
        self.stdout.flush()

        # 1. School of Computing
        school, _ = School.objects.get_or_create(name="School of Computing and Informatics", code="SCI")
        dept, _ = Department.objects.get_or_create(school=school, name="Computer Science")

        # 2. Parties (with slogan and term fields)
        parties = []
        for name, abbr, color in [("Progressive Alliance", "PA", "#FF5733"),
                                   ("Unity Front", "UF", "#33FF57"),
                                   ("Innovation Party", "IP", "#3357FF")]:
            p, _ = Party.objects.get_or_create(
                name=name, abbreviation=abbr,
                defaults={
                    'color': color,
                    'slogan': f"Vote {name} for progress!",
                    'term': "One Term"
                }
            )
            parties.append(p)

        # 3. Positions
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

        # 4. Create or get election
        now = timezone.now()
        election, _ = Election.objects.get_or_create(
            name="Student Leadership Elections 2025",
            defaults={
                'start_time': now,
                'end_time': now + timedelta(days=7),
                'is_active': True
            }
        )

        # 5. Skip clearing candidates (already done manually)
        self.stdout.write("Skipping candidate deletion (you already cleared).")
        self.stdout.flush()

        # 6. Create 100 Auto‑approved Voters – print each one
        self.stdout.write("Creating 100 voters (students)...")
        self.stdout.flush()
        for i in range(1, 101):
            adm = f"COM/B/01-{i:03d}/2022"
            user, created = User.objects.get_or_create(
                username=f"student{i}",
                defaults={
                    'first_name': f"Student{i}",
                    'last_name': "Voter",
                    'email': f"student{i}@demo.mmust.ac.ke",
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
                self.stdout.write(f"  Created voter: {user.username}")
            else:
                self.stdout.write(f"  Voter already exists: {user.username}")
            self.stdout.flush()

        self.stdout.write("Finished creating voters.\n")
        self.stdout.flush()

        # Helper to create a candidate
        def create_candidate(position_name, first_name, last_name, username_suffix, email_suffix,
                             party=None, gender=None):
            username = f"{position_name.replace(' ', '_').lower()}_{username_suffix}"
            email = f"{username}@demo.mmust.ac.ke"
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone': f"+254712345{random.randint(500,999)}",
                    'role': 'candidate',
                    'admission_number': f"COM/B/01-{random.randint(200,300):03d}/2022",
                    'course': 'Computer Science',
                    'year_of_study': 4,
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
            candidate, created = Candidate.objects.get_or_create(
                user=user, election=election, position=positions[position_name],
                defaults={
                    'party': party,
                    'verified': True,
                    'manifesto': f"I am {first_name} {last_name} and I will serve you well.",
                    'candidate_metadata': {'gender': gender} if gender else {}
                }
            )
            if created:
                self.stdout.write(f"  Created candidate: {first_name} {last_name} for {position_name}")
            return candidate

        # 7. President (Party Ticket) – 3 parties
        self.stdout.write("\nCreating presidential candidates...")
        for i, party in enumerate(parties, start=1):
            create_candidate(
                position_name="President (Party Ticket)",
                first_name=f"Pres{i}",
                last_name=party.name,
                username_suffix=f"pres_{party.abbreviation.lower()}",
                email_suffix=f"pres{i}",
                party=party,
                gender='male'
            )

        # 8. School Representative (Male) – 3 male candidates
        self.stdout.write("\nCreating School Representative (Male) candidates...")
        male_first = ["John", "Michael", "David", "James", "Robert", "William", "Joseph", "Thomas"]
        male_last = ["MaleRep", "Carter", "Smith", "Johnson", "Brown", "Williams", "Jones", "Garcia"]
        for idx in range(1, 4):
            create_candidate(
                position_name="School Representative (Male)",
                first_name=random.choice(male_first),
                last_name=random.choice(male_last),
                username_suffix=f"male_{idx}",
                email_suffix=f"male{idx}",
                gender='male'
            )

        # 9. School Representative (Female) – 3 female candidates
        self.stdout.write("\nCreating School Representative (Female) candidates...")
        female_first = ["Jane", "Mary", "Linda", "Patricia", "Jennifer", "Elizabeth", "Barbara", "Susan"]
        female_last = ["FemaleRep", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas"]
        for idx in range(1, 4):
            create_candidate(
                position_name="School Representative (Female)",
                first_name=random.choice(female_first),
                last_name=random.choice(female_last),
                username_suffix=f"female_{idx}",
                email_suffix=f"female{idx}",
                gender='female'
            )

        # 10. Halls (each with 3 competitors)
        hall_positions = [
            ("Hall 1 Representative (Male)", "hall1", "Mike", "Johnson", "male"),
            ("Hall 2 Representative (Male)", "hall2", "James", "Williams", "male"),
            ("Hall 3 Representative (Female)", "hall3", "Sarah", "Brown", "female"),
            ("Hall 4 Representative (Female)", "hall4_female", "Linda", "Jones", "female"),
            ("Hall 4 Representative (Male)", "hall4_male", "David", "Garcia", "male")
        ]
        self.stdout.write("\nCreating hall candidates...")
        for pos_name, prefix, base_first, base_last, gender in hall_positions:
            for idx in range(1, 4):
                first = f"{base_first}{idx}" if idx > 1 else base_first
                last = f"{base_last}Camp" if idx > 1 else base_last
                create_candidate(
                    position_name=pos_name,
                    first_name=first,
                    last_name=last,
                    username_suffix=f"{prefix}_{idx}",
                    email_suffix=f"{prefix}{idx}",
                    gender=gender
                )

        # 11. Non-resident Representatives (Male & Female) – 3 each
        self.stdout.write("\nCreating non-resident candidates...")
        for idx in range(1, 4):
            create_candidate(
                position_name="Non-resident Representative (Male)",
                first_name=f"Peter{idx}",
                last_name="NonResMale",
                username_suffix=f"nonres_male_{idx}",
                email_suffix=f"nonres_male{idx}",
                gender='male'
            )
            create_candidate(
                position_name="Non-resident Representative (Female)",
                first_name=f"Grace{idx}",
                last_name="NonResFemale",
                username_suffix=f"nonres_female_{idx}",
                email_suffix=f"nonres_female{idx}",
                gender='female'
            )

        # 12. Polling Officers (2)
        self.stdout.write("\nCreating polling officers...")
        for i in [1,2]:
            user, created = User.objects.get_or_create(
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

        # 13. Admin user – SKIP (assume already exists)
        self.stdout.write("Skipping admin creation (already exists).")

        self.stdout.write(self.style.SUCCESS(
            "\nDummy data generation complete! All positions have 3 competitors each."
        ))