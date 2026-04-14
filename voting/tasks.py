# voting/tasks.py

import logging
from datetime import timedelta
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Q
from webpush import send_user_notification
from .models import User, Notification, Candidate, Election, Vote, VoterStatus, AuditLog, TallyResult, Feedback
from .utils import send_notification, check_candidate_eligibility, store_face_embedding, decrypt_vote, tally_votes

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Helper for retrying tasks (Celery's built-in)
# ------------------------------------------------------------------
def retry_task(task, exc, retries=3, delay=60):
    """Helper to retry a Celery task with exponential backoff."""
    if task.request.retries < retries:
        # Exponential backoff: 60, 120, 240 seconds
        countdown = delay * (2 ** task.request.retries)
        logger.warning(f"Task {task.name} failed, retry {task.request.retries+1}/{retries} after {countdown}s")
        raise task.retry(exc=exc, countdown=countdown)
    else:
        logger.error(f"Task {task.name} failed after {retries} retries: {exc}")
        # Optionally send an alert email to admins
        # send_alert_email.delay(f"Task {task.name} failed", str(exc))
        return None

# ------------------------------------------------------------------
# Notification Tasks
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=3)
def send_notification_task(self, user_id, subject, message, send_email=True, send_sms=True):
    """Send email/SMS notification to a single user with retries."""
    logger.info(f"send_notification_task called for user {user_id}")
    try:
        user = User.objects.get(id=user_id)
        send_notification(user, subject, message, send_email, send_sms)
        # Log success
        Notification.objects.create(
            user=user,
            subject=subject,
            message=message,
            sent_via_email=send_email,
            sent_via_sms=send_sms,
            is_read=False
        )
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for notification.")
    except Exception as exc:
        # Retry on any exception (network issues, etc.)
        retry_task(self, exc)

@shared_task
def broadcast_notification_task(user_ids, subject, message, send_email=True, send_sms=True):
    """Send bulk notifications to multiple users (non-retrying)."""
    for user_id in user_ids:
        send_notification_task.delay(user_id, subject, message, send_email, send_sms)

@shared_task
def send_voting_reminders(election_id):
    """Send voting reminders to all eligible voters before election starts."""
    try:
        election = Election.objects.get(id=election_id)
        voters = User.objects.filter(role='voter', is_verified=True)
        subject = f"Voting Reminder: {election.name}"
        message = f"Voting for {election.name} starts on {election.start_time} and ends on {election.end_time}. Please log in to cast your vote."
        for voter in voters:
            send_notification_task.delay(voter.id, subject, message, send_email=True, send_sms=True)
    except Election.DoesNotExist:
        logger.error(f"Election {election_id} not found for reminders.")

# ------------------------------------------------------------------
# Face Recognition Tasks
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=2)
def process_face_embedding(self, user_id, image_data):
    """Process uploaded face image and store embedding asynchronously."""
    try:
        user = User.objects.get(id=user_id)
        embedding = store_face_embedding(image_data)  # returns binary or None
        if embedding:
            user.face_embedding = embedding
            user.save(update_fields=['face_embedding'])
            logger.info(f"Face embedding stored for user {user_id}")
        else:
            logger.warning(f"Face embedding failed for user {user_id}")
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for face embedding.")
    except Exception as exc:
        retry_task(self, exc)

@shared_task
def verify_face_task(user_id, selfie_data):
    """Compare a selfie with stored face embedding."""
    from .utils import verify_face
    try:
        user = User.objects.get(id=user_id)
        if user.face_embedding:
            match = verify_face(user.face_embedding, selfie_data)
            return match
        else:
            return False
    except User.DoesNotExist:
        return False

# ------------------------------------------------------------------
# Candidate Verification via External Portal
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=3)
def verify_candidate_eligibility(self, candidate_id):
    """Check candidate's academic record via MMUST student portal."""
    try:
        candidate = Candidate.objects.get(id=candidate_id)
        admission = candidate.user.admission_number
        # Simulate API call; replace with actual portal integration
        eligible = check_candidate_eligibility(admission)
        if not eligible:
            candidate.missing_marks = True
            candidate.supplementary_exams = True
            candidate.verified = False
        else:
            candidate.verified = True
        candidate.save()
        # Notify candidate
        subject = "Candidate Eligibility Verification"
        message = f"Your candidacy for {candidate.election.name} has been {'approved' if eligible else 'rejected'} after academic verification."
        send_notification_task.delay(candidate.user.id, subject, message, send_email=True, send_sms=True)
        return eligible
    except Candidate.DoesNotExist:
        logger.error(f"Candidate {candidate_id} not found.")
        return False
    except Exception as exc:
        retry_task(self, exc)

# ------------------------------------------------------------------
# Vote Tallying & Results
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=2)
def tally_election_results(self, election_id):
    """Decrypt and count votes for an election, then cache results."""
    try:
        election = Election.objects.get(id=election_id)
        if not election.is_closed():
            logger.warning(f"Election {election_id} is not closed yet. Tally postponed.")
            return False
        
        # Get all votes for this election
        votes = Vote.objects.filter(election=election)
        # Decrypt private key using master passphrase
        from .utils import decrypt_private_key
        private_key_pem = decrypt_private_key(election.private_key_encrypted)
        if not private_key_pem:
            raise ValueError("Failed to decrypt private key")
        
        # Tally votes
        tally_data = tally_votes(votes, private_key_pem)
        
        # Save or update TallyResult
        tally_result, created = TallyResult.objects.update_or_create(
            election=election,
            defaults={'results': tally_data}
        )
        logger.info(f"Tally completed for election {election_id}. Results cached.")
        
        # Send results to admins
        admin_users = User.objects.filter(role='admin')
        subject = f"Election Results Ready: {election.name}"
        message = f"The results for {election.name} have been tallied. Log in to the admin panel to view."
        for admin in admin_users:
            send_notification_task.delay(admin.id, subject, message, send_email=True)
        return True
    except Election.DoesNotExist:
        logger.error(f"Election {election_id} not found.")
        return False
    except Exception as exc:
        retry_task(self, exc)

# ------------------------------------------------------------------
# Automated Audit Logging
# ------------------------------------------------------------------
@shared_task
def log_audit_event(user_id, action, ip_address, user_agent, details=None):
    """Create an audit log entry asynchronously."""
    try:
        user = User.objects.get(id=user_id) if user_id else None
        AuditLog.objects.create(
            user=user,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {}
        )
    except User.DoesNotExist:
        AuditLog.objects.create(
            user=None,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {}
        )

# ------------------------------------------------------------------
# Cleanup Tasks
# ------------------------------------------------------------------
@shared_task
def cleanup_expired_sessions():
    """Remove expired Django sessions (if using database backend)."""
    from django.contrib.sessions.models import Session
    deleted, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
    logger.info(f"Deleted {deleted} expired sessions.")

@shared_task
def delete_old_audit_logs(days=90):
    """Delete audit logs older than specified days."""
    cutoff = timezone.now() - timezone.timedelta(days=days)
    deleted, _ = AuditLog.objects.filter(timestamp__lt=cutoff).delete()
    logger.info(f"Deleted {deleted} old audit logs.")

@shared_task
def delete_old_notifications(days=30):
    """Delete read notifications older than 30 days."""
    cutoff = timezone.now() - timezone.timedelta(days=days)
    deleted, _ = Notification.objects.filter(is_read=True, created_at__lt=cutoff).delete()
    logger.info(f"Deleted {deleted} old notifications.")

@shared_task
def mark_notifications_read(user_id):
    """Mark all unread notifications for a user as read."""
    updated = Notification.objects.filter(user_id=user_id, is_read=False).update(is_read=True)
    return updated

# ------------------------------------------------------------------
# Periodic Tasks (can be scheduled via Celery Beat)
# ------------------------------------------------------------------
@shared_task
def auto_verify_pending_users():
    """Auto-verify users who have uploaded valid IDs (simulated)."""
    pending_users = User.objects.filter(is_verified=False)
    for user in pending_users:
        if user.id_photo:
            # In production, call an external verification API
            user.is_verified = True
            user.save()
            send_notification_task.delay(user.id, "Account Verified", "Your account has been auto-verified.", True, True)
    logger.info(f"Auto-verified {pending_users.count()} users.")

@shared_task
def remind_non_voters(election_id):
    """Remind users who haven't voted yet (mid-election)."""
    try:
        election = Election.objects.get(id=election_id)
        if not election.is_ongoing():
            return
        voters = User.objects.filter(role='voter', is_verified=True)
        for voter in voters:
            status = VoterStatus.objects.filter(user=voter, election=election).first()
            if not status or not status.has_voted:
                subject = f"Reminder: You haven't voted in {election.name} yet"
                message = f"The election ends at {election.end_time}. Please cast your vote soon."
                send_notification_task.delay(voter.id, subject, message, True, True)
    except Election.DoesNotExist:
        logger.error(f"Election {election_id} not found for reminders.")

# ------------------------------------------------------------------
# Post-Election Result Publishing
# ------------------------------------------------------------------
@shared_task
def publish_results_to_website(election_id):
    """Generate static HTML for public results page (optional)."""
    from django.template.loader import render_to_string
    import os
    
    try:
        election = Election.objects.get(id=election_id)
        tally = TallyResult.objects.get(election=election)
        # Render results template
        context = {'election': election, 'results': tally.results}
        html_content = render_to_string('voting/public_results.html', context)
        # Save to static file (or send to CDN)
        filename = f"results_{election.id}.html"
        filepath = os.path.join(settings.MEDIA_ROOT, 'results', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(html_content)
        logger.info(f"Results published to {filepath}")
        return filepath
    except Exception as e:
        logger.exception(f"Failed to publish results for election {election_id}: {e}")
        return None

# ------------------------------------------------------------------
# Turnout Notifications (Push)
# ------------------------------------------------------------------
@shared_task
def check_turnout_threshold(election_id, voted_count, total_voters):
    """Check if turnout has reached a milestone and send push notifications to admins."""
    if total_voters == 0:
        return
    turnout = (voted_count / total_voters) * 100
    thresholds = [25, 50, 75, 90]
    # Get last notified thresholds for this election (could store in a model)
    # For simplicity, we'll use a global cache; but here we'll just check and send.
    # In production, store last notified thresholds in a Redis set or a model.
    for th in thresholds:
        if turnout >= th:
            # Check if we've already notified for this threshold (simple in-memory)
            # We'll just send; you may add a check to avoid duplicate notifications.
            for user in User.objects.filter(is_staff=True):
                try:
                    send_user_notification(user=user, payload={
                        'head': f'Turnout {int(turnout)}%',
                        'body': f'Election {election_id} has reached {int(turnout)}% turnout!'
                    }, ttl=1000)
                except Exception as e:
                    logger.error(f"Push notification failed for user {user.id}: {e}")

@shared_task
def check_ended_elections():
    """Check for elections that ended in the last minute and start tally."""
    now = timezone.now()
    cutoff = now - timedelta(minutes=1)
    ended_elections = Election.objects.filter(
        end_time__lte=now,
        end_time__gte=cutoff,
        is_active=True   # still active but just ended
    )
    for election in ended_elections:
        # Mark as inactive to prevent further voting
        election.is_active = False
        election.save()
        # Start tally (non-blocking)
        tally_election_results.delay(election.id)
        logger.info(f"Auto‑tally started for election {election.id}")
        
# ------------------------------------------------------------------
# Feedback Email (Optional: send thank-you email asynchronously)
# ------------------------------------------------------------------
@shared_task
def send_feedback_thankyou(feedback_id):
    """Send a thank-you email after feedback submission."""
    try:
        feedback = Feedback.objects.get(id=feedback_id)
        subject = "Thank you for your feedback"
        message = f"Dear {feedback.user.get_full_name()},\n\nThank you for sharing your feedback on {feedback.election.name}. We appreciate your input and will use it to improve our voting system.\n\nBest regards,\nMMUST Voting Team"
        send_mail(subject, message, settings.EMAIL_HOST_USER, [feedback.user.email], fail_silently=True)
        logger.info(f"Feedback thank-you email sent to {feedback.user.email}")
    except Feedback.DoesNotExist:
        logger.error(f"Feedback {feedback_id} not found.")