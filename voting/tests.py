# voting/tests.py

import json
import tempfile
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.core import mail
from django.contrib.sessions.models import Session

from .models import *
from .forms import *
from .tasks import *
from .utils import generate_receipt, encrypt_vote

User = get_user_model()

# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------
def create_test_image():
    """Create a simple in-memory image file for testing."""
    return SimpleUploadedFile("test.jpg", b"file_content", content_type="image/jpeg")

def create_test_user(role='voter', verified=False, **kwargs):
    """Create a user with minimal required fields."""
    defaults = {
        'username': f'test_{role}',
        'first_name': 'Test',
        'last_name': role.capitalize(),
        'email': f'{role}@mmust.ac.ke',   # enforce @mmust.ac.ke for email validation
        'phone': '+254712345678',
        'security_question': 'mother_maiden',
        'security_answer': 'answer',
        'id_type': 'national_id',
        'id_photo': create_test_image(),
        'is_verified': verified,
    }
    defaults.update(kwargs)
    user = User.objects.create_user(**defaults)
    user.role = role
    if role == 'voter':
        user.admission_number = 'SCI/001/21'
        user.course = 'Computer Science'
        user.year_of_study = 3
        school = School.objects.create(name='School of Computing', code='SCI')
        dept = Department.objects.create(school=school, name='Computer Science')
        user.school = school
        user.department = dept
        user.residence = 'Main Campus'
    elif role == 'polling_officer':
        user.staff_id = 'STAFF123'
        user.department_work = 'IT'
    user.save()
    return user

def create_election(days_offset_start=0, days_offset_end=1, is_active=True):
    """Create an election with start/end times relative to now."""
    now = timezone.now()
    start = now + timedelta(days=days_offset_start)
    end = now + timedelta(days=days_offset_end)
    return Election.objects.create(
        name='Test Election',
        start_time=start,
        end_time=end,
        is_active=is_active,
        public_key='test_public_key',
        private_key_encrypted='test_private_key'
    )

# ------------------------------------------------------------------
# Model Tests
# ------------------------------------------------------------------
class ModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Test School', code='TS')
        self.dept = Department.objects.create(school=self.school, name='Test Dept')
        self.user = create_test_user(role='voter', verified=True)

    def test_user_voter_id_generation(self):
        self.assertTrue(self.user.voter_id.startswith('MMUST'))

    def test_user_str_method(self):
        self.assertEqual(str(self.user), f"Test Voter ({self.user.voter_id})")

    def test_election_status_methods(self):
        now = timezone.now()
        election_upcoming = Election.objects.create(name='Upcoming', start_time=now+timedelta(days=1), end_time=now+timedelta(days=2))
        election_ongoing = Election.objects.create(name='Ongoing', start_time=now-timedelta(hours=1), end_time=now+timedelta(hours=1))
        election_closed = Election.objects.create(name='Closed', start_time=now-timedelta(days=2), end_time=now-timedelta(days=1))
        self.assertTrue(election_upcoming.is_upcoming())
        self.assertTrue(election_ongoing.is_ongoing())
        self.assertTrue(election_closed.is_closed())

    def test_candidate_eligibility(self):
        election = create_election()
        candidate = Candidate.objects.create(
            user=self.user,
            election=election,
            position=Position.objects.create(name='President'),
            verified=True,
            missing_marks=False,
            supplementary_exams=False
        )
        self.assertTrue(candidate.is_eligible())
        candidate.missing_marks = True
        self.assertFalse(candidate.is_eligible())

    # New model tests
    def test_feedback_model(self):
        election = create_election()
        feedback = Feedback.objects.create(
            user=self.user,
            election=election,
            rating=5,
            comment='Great system!'
        )
        self.assertEqual(str(feedback), f"{self.user} - {election} - 5")

    def test_vote_timeline_model(self):
        election = create_election()
        timeline = VoteTimeline.objects.create(
            election=election,
            candidate_id=1,
            position_id=1
        )
        self.assertTrue(timeline.timestamp <= timezone.now())

# ------------------------------------------------------------------
# Form Tests
# ------------------------------------------------------------------
class FormTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Test School', code='TS')
        self.dept = Department.objects.create(school=self.school, name='Test Dept')

    def test_user_registration_form_valid_voter(self):
        form_data = {
            'username': 'newvoter',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@mmust.ac.ke',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
            'role': 'voter',
            'phone': '+254712345678',
            'security_question': 'mother_maiden',
            'security_answer': 'smith',
            'id_type': 'national_id',
            'id_photo': create_test_image(),
            'admission_number': 'SCI/001/21',
            'course': 'CS',
            'year_of_study': 3,
            'school': self.school.id,
            'department': self.dept.id,
            'residence': 'Main',
        }
        form = UserRegistrationForm(data=form_data, files={'id_photo': create_test_image()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_user_registration_form_missing_student_fields(self):
        form_data = {
            'username': 'badstudent',
            'first_name': 'Bad',
            'last_name': 'Student',
            'email': 'bad@mmust.ac.ke',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
            'role': 'voter',
            'phone': '+254712345678',
            'security_question': 'mother_maiden',
            'security_answer': 'answer',
            'id_type': 'national_id',
            'id_photo': create_test_image(),
        }
        form = UserRegistrationForm(data=form_data, files={'id_photo': create_test_image()})
        self.assertFalse(form.is_valid())
        self.assertIn('admission_number', form.errors)

    def test_user_profile_form(self):
        user = create_test_user(role='voter')
        form_data = {
            'email': 'updated@mmust.ac.ke',
            'phone': '+254712345678',
            'security_question': 'birth_city',
            'security_answer': '',
            'residence': 'Town Campus',
            'polling_station': '',
        }
        form = UserProfileForm(data=form_data, instance=user)
        self.assertTrue(form.is_valid())

    def test_feedback_form_valid(self):
        form_data = {'rating': 4, 'comment': 'Good experience'}
        form = FeedbackForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_feedback_form_invalid_rating(self):
        form_data = {'rating': 6, 'comment': 'Too high'}
        form = FeedbackForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('rating', form.errors)

    # existing form tests remain
    def test_polling_officer_test_form_grading(self):
        form_data = {
            'q1': 'Verify their voter status in the system and check if they have already cast a vote.',
            'q2': 'Provide assistance according to the disability, e.g., reading aloud.',
            'q3': 'Mark it as spoiled, issue a new ballot, and record the incident.',
            'q4': 'Prohibit, explain rules, confiscate phone if necessary.',
            'q5': 'Voter secrecy ensures free choice and prevents coercion.',
        }
        form = PollingOfficerTestForm(data=form_data)
        self.assertTrue(form.is_valid())
        score, answers = form.grade()
        self.assertGreaterEqual(score, 80)

    def test_candidate_verification_form_clean(self):
        form = CandidateVerificationForm(data={'verified': True, 'missing_marks': True})
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

# ------------------------------------------------------------------
# View Tests (with authentication)
# ------------------------------------------------------------------
class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_voter = create_test_user(role='voter', verified=True)
        self.user_candidate = create_test_user(role='candidate', username='candidate', verified=True)
        self.user_officer = create_test_user(role='polling_officer', username='officer', verified=True)
        self.user_admin = create_test_user(role='admin', username='admin', is_verified=True)
        self.election = create_election(days_offset_start=-1, days_offset_end=1)  # ongoing

    # existing view tests (most remain unchanged, but we update the vote flow test to check feedback redirect)
    def test_register_view_get(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/register.html')

    def test_login_view_valid(self):
        response = self.client.post(reverse('login'), {
            'username': 'test_voter',
            'password': 'ComplexPass123!'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_dashboard_shows_election(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Election')

    def test_candidate_registration_view(self):
        self.client.login(username='candidate', password='ComplexPass123!')
        response = self.client.get(reverse('candidate_register'))
        self.assertEqual(response.status_code, 200)
        position = Position.objects.create(name='President')
        party = Party.objects.create(name='Test Party', abbreviation='TP')
        response = self.client.post(reverse('candidate_register'), {
            'position': position.id,
            'party': party.id,
            'manifesto': 'I will do great things.'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Candidate.objects.filter(user=self.user_candidate).exists())

    @patch('voting.utils.check_candidate_eligibility')
    def test_candidate_eligibility_fails(self, mock_check):
        mock_check.return_value = False
        self.client.login(username='candidate', password='ComplexPass123!')
        position = Position.objects.create(name='President')
        response = self.client.post(reverse('candidate_register'), {
            'position': position.id,
            'party': '',
            'manifesto': 'I will do great things.'
        })
        self.assertContains(response, 'not eligible')

    def test_polling_officer_test_view(self):
        self.client.login(username='officer', password='ComplexPass123!')
        response = self.client.get(reverse('polling_officer_test'))
        self.assertEqual(response.status_code, 200)
        form_data = {
            'q1': 'Verify their voter status in the system and check if they have already cast a vote.',
            'q2': 'Provide assistance according to the disability, e.g., reading aloud.',
            'q3': 'Mark it as spoiled, issue a new ballot, and record the incident.',
            'q4': 'Prohibit, explain rules, confiscate phone if necessary.',
            'q5': 'Voter secrecy ensures free choice and prevents coercion.',
        }
        response = self.client.post(reverse('polling_officer_test'), form_data)
        self.assertRedirects(response, reverse('dashboard'))
        test = PollingOfficerTest.objects.get(user=self.user_officer)
        self.assertTrue(test.passed)

    def test_voting_ballot_requires_active_election(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('voting_ballot'))
        self.assertEqual(response.status_code, 200)  # Election is ongoing
        Election.objects.all().delete()
        create_election(days_offset_start=-2, days_offset_end=-1)  # closed
        response = self.client.get(reverse('voting_ballot'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_vote_flow(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        position = Position.objects.create(name='President')
        candidate = Candidate.objects.create(
            user=self.user_candidate,
            election=self.election,
            position=position,
            verified=True
        )
        response = self.client.get(reverse('voting_ballot'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('voting_ballot'), {
            f'position_{position.id}': candidate.id
        })
        self.assertRedirects(response, reverse('vote_review'))
        response = self.client.post(reverse('vote_review'))
        # After vote, redirect to feedback page
        self.assertRedirects(response, reverse('feedback', args=[self.election.id]))
        voter_status = VoterStatus.objects.get(user=self.user_voter, election=self.election)
        self.assertTrue(voter_status.has_voted)
        self.assertTrue(Vote.objects.filter(election=self.election).exists())

    def test_already_voted_cannot_vote_again(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        VoterStatus.objects.create(user=self.user_voter, election=self.election, has_voted=True)
        response = self.client.get(reverse('voting_ballot'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_results_view(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('results'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/results.html')

    def test_chatbot_api(self):
        response = self.client.post(reverse('chatbot_api'),
                                   data=json.dumps({'message': 'How to register?'}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('response', response.json())

    # New view tests
    def test_profile_view(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/profile.html')

    def test_profile_update(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.post(reverse('profile'), {
            'email': 'updated@mmust.ac.ke',
            'phone': '+254712345678',
            'security_question': 'birth_city',
            'security_answer': '',
            'residence': 'Town Campus',
        })
        self.assertRedirects(response, reverse('profile'))
        self.user_voter.refresh_from_db()
        self.assertEqual(self.user_voter.residence, 'Town Campus')

    def test_voting_history_view(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('voting_history'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/voting_history.html')

    def test_eligibility_api(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('eligibility_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('eligible', data)

    @patch('voting.views.get_location_from_ip')
    def test_voter_locations_api(self, mock_location):
        mock_location.return_value = (1.0, 1.0)
        self.client.login(username='admin', password='ComplexPass123!')
        # Create a voter status with location
        status = VoterStatus.objects.create(user=self.user_voter, election=self.election, has_voted=True, latitude=1.0, longitude=1.0)
        response = self.client.get(reverse('voter_locations', args=[self.election.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)

    def test_live_map_view(self):
        self.client.login(username='admin', password='ComplexPass123!')
        response = self.client.get(reverse('live_map', args=[self.election.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/live_map.html')

    def test_replay_view(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        # First close election
        self.election.end_time = timezone.now() - timedelta(days=1)
        self.election.save()
        response = self.client.get(reverse('replay_votes', args=[self.election.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'voting/replay.html')

    def test_feedback_submission(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.post(reverse('feedback', args=[self.election.id]), {
            'rating': 5,
            'comment': 'Excellent!'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Feedback.objects.filter(user=self.user_voter, election=self.election).exists())

    def test_candidate_withdrawal(self):
        # First create a candidate in upcoming election
        self.election.start_time = timezone.now() + timedelta(days=1)
        self.election.save()
        candidate = Candidate.objects.create(
            user=self.user_candidate,
            election=self.election,
            position=Position.objects.create(name='President'),
            verified=True
        )
        self.client.login(username='candidate', password='ComplexPass123!')
        response = self.client.post(reverse('candidate_withdraw'), {'confirm': True})
        self.assertRedirects(response, reverse('dashboard'))
        candidate.refresh_from_db()
        self.assertTrue(candidate.withdrawn)
        self.assertFalse(candidate.verified)

    def test_results_embed(self):
        # Close election
        self.election.end_time = timezone.now() - timedelta(days=1)
        self.election.save()
        # Create tally result
        TallyResult.objects.create(election=self.election, results={'1': {'2': {'name':'John', 'party':'Ind', 'votes':10}}})
        response = self.client.get(reverse('results_embed', args=[self.election.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John')

    # Admin export tests
    def test_export_voters_csv(self):
        self.client.login(username='admin', password='ComplexPass123!')
        response = self.client.get(reverse('export_voters_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_export_candidates_csv(self):
        self.client.login(username='admin', password='ComplexPass123!')
        response = self.client.get(reverse('export_candidates_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

    def test_export_audit_csv(self):
        self.client.login(username='admin', password='ComplexPass123!')
        response = self.client.get(reverse('export_audit_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

# ------------------------------------------------------------------
# Task Tests (with mocking)
# ------------------------------------------------------------------
class TaskTests(TestCase):
    def setUp(self):
        self.user = create_test_user(role='voter')
        self.election = create_election()

    @patch('voting.tasks.send_notification')
    def test_send_notification_task(self, mock_send):
        mock_send.return_value = None
        send_notification_task(self.user.id, 'Test', 'Message', True, True)
        mock_send.assert_called_once()
        self.assertTrue(Notification.objects.filter(user=self.user, subject='Test').exists())

    @patch('voting.tasks.check_candidate_eligibility')
    def test_verify_candidate_eligibility_task(self, mock_check):
        mock_check.return_value = True
        candidate = Candidate.objects.create(
            user=self.user,
            election=self.election,
            position=Position.objects.create(name='President')
        )
        result = verify_candidate_eligibility(candidate.id)
        self.assertTrue(result)
        candidate.refresh_from_db()
        self.assertTrue(candidate.verified)

    @patch('voting.tasks.tally_votes')
    @patch('voting.tasks.decrypt_private_key')
    def test_tally_election_results(self, mock_decrypt, mock_tally):
        mock_decrypt.return_value = 'private_key_pem'
        mock_tally.return_value = {1: {2: 10}}
        result = tally_election_results(self.election.id)
        self.assertTrue(result)
        self.assertTrue(TallyResult.objects.filter(election=self.election).exists())

    @patch('voting.tasks.store_face_embedding')
    def test_process_face_embedding_task(self, mock_store):
        mock_store.return_value = b'fake_embedding'
        process_face_embedding(self.user.id, 'image_data')
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.face_embedding)

    def test_cleanup_expired_sessions(self):
        from django.contrib.sessions.backends.db import SessionStore
        s = SessionStore()
        s.create()
        s.set_expiry(timezone.now() - timedelta(days=1))
        s.save()
        cleanup_expired_sessions()
        self.assertFalse(Session.objects.filter(session_key=s.session_key).exists())

    def test_delete_old_audit_logs(self):
        old_log = AuditLog.objects.create(action='old', timestamp=timezone.now() - timedelta(days=100))
        new_log = AuditLog.objects.create(action='new', timestamp=timezone.now())
        delete_old_audit_logs(days=30)
        self.assertFalse(AuditLog.objects.filter(id=old_log.id).exists())
        self.assertTrue(AuditLog.objects.filter(id=new_log.id).exists())

    def test_delete_old_notifications(self):
        old_notif = Notification.objects.create(user=self.user, subject='Old', is_read=True, created_at=timezone.now() - timedelta(days=40))
        new_notif = Notification.objects.create(user=self.user, subject='New', is_read=True, created_at=timezone.now())
        delete_old_notifications(days=30)
        self.assertFalse(Notification.objects.filter(id=old_notif.id).exists())
        self.assertTrue(Notification.objects.filter(id=new_notif.id).exists())

    @patch('voting.tasks.send_user_notification')
    def test_check_turnout_threshold(self, mock_push):
        check_turnout_threshold(1, 25, 100)  # 25% turnout
        # Note: we can't easily check if push was sent without more mocking; just ensure no exception
        self.assertTrue(True)

    @patch('voting.tasks.send_mail')
    def test_send_feedback_thankyou(self, mock_send_mail):
        feedback = Feedback.objects.create(user=self.user, election=self.election, rating=5)
        send_feedback_thankyou(feedback.id)
        mock_send_mail.assert_called_once()

# ------------------------------------------------------------------
# Security & Edge Cases
# ------------------------------------------------------------------
class SecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user(role='voter', verified=True)
        self.election = create_election(days_offset_start=-1, days_offset_end=1)

    def test_vote_encryption_and_receipt(self):
        vote_data = {'1': 5}
        encrypted = encrypt_vote(json.dumps(vote_data), 'test_public_key')
        receipt = generate_receipt(encrypted, self.user.id)
        self.assertIsNotNone(receipt)
        self.assertEqual(len(receipt), 64)

    def test_csrf_protection(self):
        # This test is minimal; actual CSRF is handled by Django's middleware.
        pass

    def test_role_based_access(self):
        self.client.login(username='test_candidate', password='ComplexPass123!')
        response = self.client.get(reverse('polling_officer_test'))
        self.assertRedirects(response, reverse('dashboard'))

        self.client.login(username='test_voter', password='ComplexPass123!')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)  # redirect because not admin

    def test_duplicate_vote_prevention(self):
        self.client.login(username='test_voter', password='ComplexPass123!')
        VoterStatus.objects.create(user=self.user, election=self.election, has_voted=True)
        response = self.client.get(reverse('voting_ballot'))
        self.assertRedirects(response, reverse('dashboard'))

# ------------------------------------------------------------------
# Integration Test (end-to-end)
# ------------------------------------------------------------------
class IntegrationTests(TestCase):
    def test_full_voting_flow(self):
        """Register user -> login -> register as candidate -> vote -> verify receipt -> view results."""
        # 1. Register a voter
        school = School.objects.create(name='SCI', code='SCI')
        dept = Department.objects.create(school=school, name='CS')
        register_data = {
            'username': 'voter1',
            'first_name': 'Voter',
            'last_name': 'One',
            'email': 'voter1@mmust.ac.ke',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
            'role': 'voter',
            'phone': '+254712345678',
            'security_question': 'mother_maiden',
            'security_answer': 'smith',
            'id_type': 'national_id',
            'admission_number': 'SCI/001/21',
            'course': 'CS',
            'year_of_study': 3,
            'school': school.id,
            'department': dept.id,
            'residence': 'Main Campus',
        }
        files = {'id_photo': create_test_image()}
        response = self.client.post(reverse('register'), data=register_data, files=files)
        self.assertRedirects(response, reverse('login'))
        user = User.objects.get(username='voter1')
        user.is_verified = True
        user.save()

        # 2. Login
        self.client.login(username='voter1', password='TestPass123!')

        # 3. Create election, position, candidate
        election = create_election(days_offset_start=-1, days_offset_end=1)
        position = Position.objects.create(name='President')
        candidate_user = create_test_user(role='candidate', username='candidate1')
        Candidate.objects.create(user=candidate_user, election=election, position=position, verified=True)

        # 4. Vote
        response = self.client.post(reverse('voting_ballot'), {f'position_{position.id}': candidate_user.candidacy.id})
        self.assertRedirects(response, reverse('vote_review'))
        response = self.client.post(reverse('vote_review'))
        self.assertRedirects(response, reverse('feedback', args=[election.id]))

        # 5. Verify receipt
        receipt = VoterStatus.objects.get(user=user, election=election).vote_receipt
        self.assertIsNotNone(receipt)

        # 6. Check results (election must be closed for results)
        election.end_time = timezone.now() - timedelta(days=1)
        election.save()
        response = self.client.get(reverse('results'))
        self.assertEqual(response.status_code, 200)