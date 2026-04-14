# voting/signals.py

from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from .models import Election, VoterStatus, Notification, Candidate, Feedback, PollingOfficerTest, AuditLog
from .utils import send_notification
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# ------------------------------------------------------------------
# Pre-save to capture old verification status for User
# ------------------------------------------------------------------
@receiver(pre_save, sender=User)
def capture_old_user_verified(sender, instance, **kwargs):
    """Store the previous is_verified value before saving."""
    if instance.pk:
        try:
            old_instance = User.objects.get(pk=instance.pk)
            instance._old_is_verified = old_instance.is_verified
        except User.DoesNotExist:
            instance._old_is_verified = False
    else:
        instance._old_is_verified = False

# ------------------------------------------------------------------
# Send welcome notification when a user becomes verified
# ------------------------------------------------------------------
@receiver(post_save, sender=User)
def send_welcome_notification(sender, instance, created, **kwargs):
    """Send email/SMS to user when their account is verified."""
    if not created and hasattr(instance, '_old_is_verified'):
        if not instance._old_is_verified and instance.is_verified:
            send_notification(
                instance,
                "Account Verified",
                "Your account has been verified. You can now vote in active elections.",
                send_email=True,
                send_sms=True
            )

# ------------------------------------------------------------------
# Pre-save for Candidate to capture old verified status
# ------------------------------------------------------------------
@receiver(pre_save, sender=Candidate)
def capture_old_candidate_verified(sender, instance, **kwargs):
    """Store previous verified status of a candidate."""
    if instance.pk:
        try:
            old = Candidate.objects.get(pk=instance.pk)
            instance._old_verified = old.verified
        except Candidate.DoesNotExist:
            instance._old_verified = False
    else:
        instance._old_verified = False

# ------------------------------------------------------------------
# Notify candidate when verification status changes
# ------------------------------------------------------------------
@receiver(post_save, sender=Candidate)
def notify_candidate_on_verification(sender, instance, created, **kwargs):
    """Send email to candidate when their candidacy is verified or rejected."""
    if not created and hasattr(instance, '_old_verified'):
        if instance._old_verified != instance.verified:
            if instance.verified:
                subject = "Candidacy Verified"
                message = f"Congratulations! Your candidacy for {instance.election.name} (Position: {instance.position.name}) has been verified. You are now on the ballot."
            else:
                subject = "Candidacy Not Verified"
                message = f"Your candidacy for {instance.election.name} (Position: {instance.position.name}) could not be verified. Please contact the election committee for details."
            send_notification(instance.user, subject, message, send_email=True, send_sms=True)

# ------------------------------------------------------------------
# Existing signals (unchanged but kept for completeness)
# ------------------------------------------------------------------
@receiver(post_save, sender=User)
def create_voter_status_for_new_elections(sender, instance, created, **kwargs):
    if created:
        active_elections = Election.objects.filter(is_active=True)
        for election in active_elections:
            VoterStatus.objects.get_or_create(user=instance, election=election)

@receiver(post_save, sender=Election)
def create_voter_status_for_new_election(sender, instance, created, **kwargs):
    if created:
        users = User.objects.filter(is_verified=True)
        for user in users:
            VoterStatus.objects.get_or_create(user=user, election=instance)

@receiver(post_save, sender=Feedback)
def send_feedback_thank_you(sender, instance, created, **kwargs):
    if created:
        send_notification(
            instance.user,
            "Thank You for Your Feedback",
            f"Thank you for participating in the MMUST Voting System. Your feedback on {instance.election.name} (Rating: {instance.rating}) is appreciated.",
            send_email=True,
            send_sms=False
        )

@receiver(pre_delete, sender=User)
def log_user_deletion(sender, instance, **kwargs):
    AuditLog.objects.create(
        user=None,
        action=f"User deleted: {instance.username} ({instance.email})",
        ip_address=None,
        user_agent=None,
        details={'voter_id': instance.voter_id, 'role': instance.role}
    )

# ------------------------------------------------------------------
# Admin notifications for new registrations, candidate applications, test passes
# ------------------------------------------------------------------
@receiver(post_save, sender=User)
def notify_admins_new_registration(sender, instance, created, **kwargs):
    if created:
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                subject=f"New User Registration: {instance.username}",
                message=f"A new user ({instance.get_full_name()}) with role {instance.get_role_display()} has registered. Please verify.",
                sent_via_email=False,
                sent_via_sms=False,
                is_read=False
            )
            send_mail(
                f"New Registration on MMUST Voting System",
                f"User: {instance.username}\nRole: {instance.get_role_display()}\nPlease log in to verify.",
                settings.EMAIL_HOST_USER,
                [admin.email],
                fail_silently=True
            )

@receiver(post_save, sender=Candidate)
def notify_admins_candidate_application(sender, instance, created, **kwargs):
    if created:
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                subject=f"Candidate Application: {instance.user.get_full_name()}",
                message=f"{instance.user.get_full_name()} has applied for {instance.position.name} in {instance.election.name}.",
                sent_via_email=False,
                sent_via_sms=False,
                is_read=False
            )
            send_mail(
                f"New Candidate Application",
                f"Candidate: {instance.user.get_full_name()}\nPosition: {instance.position.name}\nElection: {instance.election.name}\nPlease review.",
                settings.EMAIL_HOST_USER,
                [admin.email],
                fail_silently=True
            )

@receiver(post_save, sender=PollingOfficerTest)
def notify_admins_test_completion(sender, instance, **kwargs):
    if instance.passed:
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                subject=f"Polling Officer Test Passed: {instance.user.get_full_name()}",
                message=f"{instance.user.get_full_name()} has passed the qualification test with {instance.score}%. Ready for verification.",
                sent_via_email=False,
                sent_via_sms=False,
                is_read=False
            )