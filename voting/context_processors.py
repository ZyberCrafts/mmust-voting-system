# voting/context_processors.py

from django.conf import settings
from django.utils import timezone
from .models import Election, Notification

def active_election(request):
    """Inject the current active election into all templates."""
    now = timezone.now()
    election = Election.objects.filter(
        start_time__lte=now,
        end_time__gte=now,
        is_active=True
    ).first()
    return {'active_election': election}

def site_settings(request):
    """Site‑wide settings (name, logo, year, debug)."""
    return {
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'MMUST Voting System'),
        'SITE_LOGO': getattr(settings, 'SITE_LOGO', '/static/images/logo.png'),
        'CURRENT_YEAR': timezone.now().year,
        'DEBUG_MODE': settings.DEBUG,
    }

def notifications_count(request):
    """Number of unread notifications for the logged‑in user."""
    if request.user.is_authenticated:
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}

def user_context(request):
    """User‑specific flags and display values."""
    user = request.user
    context = {
        'user_is_authenticated': user.is_authenticated,
        'user_role_display': user.get_role_display() if user.is_authenticated else '',
        'user_is_verified': user.is_verified if user.is_authenticated else False,
    }

    if user.is_authenticated:
        # Pending verification flag
        context['user_pending_verification'] = not user.is_verified

        # Candidate info (if candidate)
        if hasattr(user, 'candidacy') and user.candidacy:
            context['user_is_candidate'] = True
            context['user_candidacy'] = user.candidacy
        else:
            context['user_is_candidate'] = False

        # Polling officer test status
        if user.role == 'polling_officer':
            try:
                test = user.polling_officer_test
                context['user_test_passed'] = test.passed
                context['user_test_score'] = test.score
            except:
                context['user_test_passed'] = False
                context['user_test_score'] = None

        # Voting status for the active election
        election = active_election(request)['active_election']
        if election:
            try:
                voter_status = user.voting_status.get(election=election)
                context['user_has_voted'] = voter_status.has_voted
            except:
                context['user_has_voted'] = False
        else:
            context['user_has_voted'] = False

        # Admin flag
        context['user_is_admin'] = user.is_staff or user.role == 'admin'

    return context