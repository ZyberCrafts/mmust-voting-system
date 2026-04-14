from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import AttackLog

@shared_task
def notify_admins_attack(attack_type, severity, description, request_info):
    """
    Send email/SMS to all admins about a critical attack.
    request_info is a dict with necessary info.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    admins = User.objects.filter(is_staff=True)
    subject = f"[SECURITY] Critical Attack Detected: {attack_type.upper()}"
    message = f"""
    A potential {attack_type} attack was detected.

    Severity: {severity}
    Description: {description}
    IP: {request_info.get('ip')}
    Path: {request_info.get('path')}
    Method: {request_info.get('method')}
    User Agent: {request_info.get('user_agent')}
    User: {request_info.get('user')}

    Please log in to the admin panel to review.
    """
    for admin in admins:
        send_mail(subject, message, settings.EMAIL_HOST_USER, [admin.email], fail_silently=True)