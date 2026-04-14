from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import RatingSession, NotificationLog
from voting.models import VoterStatus
import requests

@shared_task
def send_rating_reminders(session_id):
    """Send email/SMS reminders for a rating session."""
    session = RatingSession.objects.get(id=session_id)
    # Get all users who voted in the election (eligible to rate)
    voters = VoterStatus.objects.filter(election=session.election, has_voted=True).select_related('user')
    link = f"{settings.SITE_URL}/accountability/questionnaire/{session_id}/"

    for status in voters:
        user = status.user
        # Avoid duplicate sends
        if NotificationLog.objects.filter(session=session, user=user).exists():
            continue

        # Email
        if user.email:
            send_mail(
                f"Rate your leaders: {session.election.name}",
                f"Hello {user.get_full_name()},\n\nPlease rate your elected leaders based on their manifesto promises.\n{link}\n\nThank you.",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=True
            )
        # SMS (optional)
        if user.phone and hasattr(settings, 'SMS_API_KEY'):
            try:
                url = "https://api.africastalking.com/version1/messaging"
                headers = {"ApiKey": settings.SMS_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
                data = {
                    "username": settings.SMS_USERNAME,
                    "to": user.phone,
                    "message": f"Rate your leaders: {session.election.name} – {link}"
                }
                requests.post(url, headers=headers, data=data, timeout=10)
            except Exception as e:
                pass

        NotificationLog.objects.create(session=session, user=user, type='email')