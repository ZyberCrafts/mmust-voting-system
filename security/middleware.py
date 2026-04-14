import logging
from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import PermissionDenied
from django.conf import settings
from .detector import scan_request, log_attack, check_rate_limit
from .models import AttackLog

logger = logging.getLogger(__name__)

# ---------- Whitelist of safe paths that skip attack scanning ----------
SAFE_PATHS = [
    '/admin-panel/broadcast/',
    '/admin-panel/test-email/',
    '/admin-panel/test-sms/',
    '/api/face/register/',
    '/api/face/verify/',
    '/candidate/register/',
    '/register/',
]

class SecurityMiddleware(MiddlewareMixin):
    """
    Inspect every request for attacks and rate limiting.
    """
    def process_request(self, request):
        # Skip scanning for safe paths (using startswith to avoid trailing slash issues)
        safe = any(request.path.startswith(path) for path in SAFE_PATHS)
        if safe:
            logger.debug(f"Skipping security scan for {request.path}")
            return None

        # Rate limiting
        ip = request.META.get('REMOTE_ADDR')
        allowed, count = check_rate_limit(ip)
        if not allowed:
            log_attack(
                attack_type='dos',
                severity=3,
                description=f'Rate limit exceeded: {count} requests in window',
                request=request,
                blocked=True
            )
            raise PermissionDenied("Too many requests. Please try again later.")

        # Scan for attacks
        attack_type, severity, description, snippet = scan_request(request)
        if attack_type:
            log_attack(
                attack_type=attack_type,
                severity=severity,
                description=description,
                request=request,
                data_snippet=snippet,
                blocked=False   # We don't block by default; you can set to True to block
            )
            # Optional: if severity >= 3, you can raise an exception
            # if severity >= 3:
            #     raise PermissionDenied("Suspicious activity detected.")
            
    def process_exception(self, request, exception):
        # Handle IDOR detection via 403
        if isinstance(exception, PermissionDenied):
            # Check if user is authenticated but got 403 (possible IDOR)
            if request.user.is_authenticated:
                log_attack(
                    attack_type='idor',
                    severity=2,
                    description=f'Forbidden access to {request.path}',
                    request=request,
                    blocked=True
                )
        return None