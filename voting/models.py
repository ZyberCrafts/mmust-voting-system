# voting/models.py (corrected)

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import os

# ------------------------------------------------------------
# Custom User Model
# ------------------------------------------------------------
class User(AbstractUser):
    """Custom user model with roles and voting-specific fields."""
    ROLES = (
        ('voter', 'Voter'),
        ('candidate', 'Candidate'),
        ('polling_officer', 'Polling Officer'),
        ('admin', 'Admin'),
        ('board', 'Board Member'),
    )
    ID_TYPES = (
        ('national_id', 'National ID'),
        ('birth_cert', 'Birth Certificate'),
        ('school_id', 'School ID'),
    )
    SECURITY_QUESTIONS = (
        ('mother_maiden', "What is your mother's maiden name?"),
        ('first_school', "What is the name of your first primary school?"),
        ('pet_name', "What was the name of your first pet?"),
        ('birth_city', "In which city were you born?"),
        ('favorite_teacher', "Who was your favorite teacher in high school?"),
    )

    role = models.CharField(max_length=20, choices=ROLES, default='voter')
    voter_id = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    phone = models.CharField(max_length=15, help_text=_("Mobile phone number for SMS notifications"))
    security_question = models.CharField(max_length=255, choices=SECURITY_QUESTIONS)
    security_answer = models.CharField(max_length=255)
    id_type = models.CharField(max_length=20, choices=ID_TYPES)
    id_photo = models.ImageField(upload_to='ids/', help_text=_("Upload a clear photo of your ID"))
    face_embedding = models.BinaryField(null=True, blank=True, help_text=_("Face embedding for verification"))
    is_verified = models.BooleanField(default=False, help_text=_("Has the user been verified by admin?"))

    # Student fields (for voters)
    admission_number = models.CharField(max_length=20, blank=True, db_index=True)
    course = models.CharField(max_length=100, blank=True)
    year_of_study = models.IntegerField(null=True, blank=True)
    school = models.ForeignKey('School', on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    residence = models.CharField(max_length=100, blank=True, help_text=_("e.g., Main Campus, Town Campus"))
    polling_station = models.CharField(max_length=100, blank=True, help_text=_("Physical voting venue"))

    # Staff fields (for polling officers)
    staff_id = models.CharField(max_length=20, blank=True)
    department_work = models.CharField(max_length=100, blank=True, help_text=_("Department where the staff works"))

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['voter_id']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['role']),
            models.Index(fields=['admission_number']),
        ]

    def save(self, *args, **kwargs):
        # Generate voter_id if not set
        if not self.voter_id:
            self.voter_id = f"MMUST{timezone.now().strftime('%Y%m%d%H%M%S')}"
            super().save(*args, **kwargs)
            # Append primary key to make it truly unique
            self.voter_id = f"MMUST{timezone.now().strftime('%Y%m%d%H%M%S')}{self.pk}"
            super().save(update_fields=['voter_id'])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name()} ({self.voter_id})"


# ------------------------------------------------------------
# Academic Structure
# ------------------------------------------------------------
class School(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Department(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['school', 'name']
        unique_together = ['school', 'name']

    def __str__(self):
        return f"{self.school.name} - {self.name}"


# ------------------------------------------------------------
# Election Configuration
# ------------------------------------------------------------
class Position(models.Model):
    name = models.CharField(max_length=100)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True, related_name='positions')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name='positions')

    class Meta:
        ordering = ['school__name', 'department__name', 'name']
        unique_together = [['name', 'school', 'department']]

    def __str__(self):
        if self.school:
            if self.department:
                return f"{self.name} ({self.department.name})"
            return f"{self.name} ({self.school.name})"
        return self.name


class Party(models.Model):
    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)
    logo = models.ImageField(upload_to='parties/', blank=True)
    color = models.CharField(max_length=7, default='#000000', help_text='Hex color code for party theme')
    description = models.TextField(blank=True)
    slogan = models.CharField(max_length=200, blank=True, help_text="Party slogan or motto")
    term = models.CharField(max_length=50, blank=True, help_text="e.g., One Term, Two Terms")

    class Meta:
        verbose_name_plural = 'Parties'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class Election(models.Model):
    TALLY_METHODS = (
        ('homomorphic', 'Homomorphic Encryption'),
        ('mixnet', 'Mixnet'),
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    public_key = models.TextField(blank=True)
    private_key_encrypted = models.TextField(blank=True)
    tally_method = models.CharField(max_length=20, choices=TALLY_METHODS, default='homomorphic')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time.date()})"

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError(_("End time must be after start time."))

    def is_ongoing(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    def is_upcoming(self):
        return timezone.now() < self.start_time

    def is_closed(self):
        return timezone.now() > self.end_time


# ------------------------------------------------------------
# Candidates & Verification
# ------------------------------------------------------------
class Candidate(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='candidacy')
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='candidates')
    position = models.ForeignKey(Position, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.SET_NULL, null=True, blank=True)
    manifesto = models.TextField(blank=True)
    verified = models.BooleanField(default=False)
    missing_marks = models.BooleanField(default=False)
    supplementary_exams = models.BooleanField(default=False)
    withdrawn = models.BooleanField(default=False, help_text="Has the candidate withdrawn from the election?")
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_candidates')
    verified_at = models.DateTimeField(null=True, blank=True)
    is_winner = models.BooleanField(default=False, help_text="Was this candidate elected?")
    party_nomination_certificate = models.FileField(upload_to='certs/', blank=True, null=True, help_text="Signed party nomination letter")
    fee_statement = models.FileField(upload_to='fee_statements/', blank=True, null=True, help_text="Official fee statement (PDF)")
    has_cleared_fees = models.BooleanField(default=False, help_text="Admin: has cleared all fees?")
    questionnaire_completed = models.BooleanField(default=False)
    questionnaire_answers = models.JSONField(default=dict, blank=True)
    candidate_metadata = models.JSONField(default=dict, blank=True, help_text="Stores additional info like gender, hall, school, etc.")
    eligibility_pending = models.BooleanField(default=False, help_text="Manual eligibility verification required?")
    
    class Meta:
        unique_together = ['election', 'user']
        ordering = ['position', 'user__last_name']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.position.name} ({self.election.name})"

    def is_eligible(self):
        return self.verified and not (self.missing_marks or self.supplementary_exams)


class CandidateQuestion(models.Model):
    QUESTION_TYPES = (
        ('text', 'Text Answer'),
        ('boolean', 'Yes/No'),
        ('file', 'File Upload'),
    )
    question_text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, default='text')
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question_text


# ------------------------------------------------------------
# Voting Process
# ------------------------------------------------------------
class Vote(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='votes')  # removed default
    encrypted_vote = models.TextField()
    receipt_id = models.CharField(max_length=64, unique=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Vote for {self.election.name} (Receipt: {self.receipt_id[:8]}...)"


class VoterStatus(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='voting_status')
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='voter_statuses')  # removed default
    has_voted = models.BooleanField(default=False)
    vote_receipt = models.CharField(max_length=64, blank=True)
    voted_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ['user', 'election']
        indexes = [
            models.Index(fields=['user', 'election']),
            models.Index(fields=['has_voted']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.election.name}: {'Voted' if self.has_voted else 'Not voted'}"


# ------------------------------------------------------------
# Polling Officer Qualification
# ------------------------------------------------------------
class PollingOfficerTest(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='polling_officer_test')
    score = models.IntegerField()
    passed = models.BooleanField(default=False)
    answers = models.JSONField(default=dict)
    taken_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - Score: {self.score}%"


# ------------------------------------------------------------
# Notifications & Audit
# ------------------------------------------------------------
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sent_via_email = models.BooleanField(default=False)
    sent_via_sms = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.subject[:50]}"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"


# ------------------------------------------------------------
# Tally Results
# ------------------------------------------------------------
class TallyResult(models.Model):
    election = models.OneToOneField(Election, on_delete=models.CASCADE, related_name='tally_result')
    results = models.JSONField(default=dict)
    calculated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Results for {self.election.name}"


# ------------------------------------------------------------
# Feedback & Timeline (NEW)
# ------------------------------------------------------------
class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    election = models.ForeignKey(Election, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.election} - {self.rating}"


class VoteTimeline(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='timeline')
    timestamp = models.DateTimeField(auto_now_add=True)
    candidate_id = models.IntegerField()
    position_id = models.IntegerField()

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.election} - {self.timestamp}"
    
class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} - {self.subject[:50]}"
   
@classmethod
def get_pending_verifications_count(cls):
    return cls.objects.filter(is_verified=False).count()

@classmethod
def get_pending_voters_count(cls):
    return cls.objects.filter(role='voter', is_verified=False).count()

@classmethod
def get_pending_candidates_count(cls):
    return cls.objects.filter(role='candidate', is_verified=False).count()

@classmethod
def get_pending_polling_officers_count(cls):
    # Only those who have passed the test (if test exists) and not verified
    from .models import PollingOfficerTest
    return cls.objects.filter(
        role='polling_officer',
        is_verified=False,
        polling_officer_test__passed=True
    ).count()