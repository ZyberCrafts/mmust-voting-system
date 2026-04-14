# voting/decorators.py

from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

def role_required(allowed_roles=None, login_url=None, raise_exception=False):
    """
    Decorator to restrict access to users with specific roles.

    Args:
        allowed_roles (list): List of roles allowed to access the view.
        login_url (str): URL to redirect unauthenticated users. Defaults to LOGIN_URL.
        raise_exception (bool): If True, raise PermissionDenied instead of redirecting.
    """
    if allowed_roles is None:
        allowed_roles = []

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check authentication
            if not request.user.is_authenticated:
                if raise_exception:
                    raise PermissionDenied("You must be logged in.")
                return redirect(login_url or settings.LOGIN_URL)

            # Check if user is active (optional)
            if not request.user.is_active:
                if raise_exception:
                    raise PermissionDenied("Your account is inactive.")
                return redirect(login_url or settings.LOGIN_URL)

            # Check role
            if request.user.role not in allowed_roles:
                if raise_exception:
                    raise PermissionDenied("You do not have permission to access this page.")
                # Redirect to login (or a permission denied page)
                return redirect(login_url or settings.LOGIN_URL)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def enforce_2fa(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            if not request.user.totpdevice_set.filter(confirmed=True).exists():
                messages.warning(request, "You must set up Two‑Factor Authentication first.")
                return redirect('admin_2fa_setup')
        return view_func(request, *args, **kwargs)
    return wrapper

# ------------------------------------------------------------------
# Shortcuts for common roles
# ------------------------------------------------------------------
def admin_required(view_func=None, login_url=None, raise_exception=False):
    """Decorator for admin-only access."""
    if view_func is None:
        # Allow optional arguments without parentheses
        return lambda vf: admin_required(vf, login_url, raise_exception)
    return role_required(['admin'], login_url, raise_exception)(view_func)

def polling_officer_required(view_func=None, login_url=None, raise_exception=False):
    """Decorator for polling officer or admin access."""
    if view_func is None:
        return lambda vf: polling_officer_required(vf, login_url, raise_exception)
    return role_required(['polling_officer', 'admin'], login_url, raise_exception)(view_func)

def candidate_required(view_func=None, login_url=None, raise_exception=False):
    """Decorator for candidate access."""
    if view_func is None:
        return lambda vf: candidate_required(vf, login_url, raise_exception)
    return role_required(['candidate'], login_url, raise_exception)(view_func)

def voter_required(view_func=None, login_url=None, raise_exception=False):
    """Decorator for voter access."""
    if view_func is None:
        return lambda vf: voter_required(vf, login_url, raise_exception)
    return role_required(['voter', 'candidate', 'polling_officer', 'board', 'admin'], 
                         login_url, raise_exception)(view_func)

def board_required(view_func=None, login_url=None, raise_exception=False):
    """Decorator for board member access."""
    if view_func is None:
        return lambda vf: board_required(vf, login_url, raise_exception)
    return role_required(['board', 'admin'], login_url, raise_exception)(view_func)
