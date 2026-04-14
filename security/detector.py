import re
import logging
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from .models import AttackLog

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Detection rules
# ------------------------------------------------------------------
SQLI_PATTERNS = [
    r"(\%27)|(\')|(\-\-)|(\%23)|(#)",          # single quote, comment
    r"(?i)(select|insert|update|delete|drop|union|create|alter|truncate|where|from)",
    r"(\bOR\b.*=)|(\bAND\b.*=)",
    r"(\%27\s+or\s+1=1)",
    r"(\%27\s+and\s+1=1)",
]
SQLI_COMPILED = [re.compile(p, re.IGNORECASE) for p in SQLI_PATTERNS]

XSS_PATTERNS = [
    r"(?i)(<script|javascript:|onerror=|onload=|alert\(|confirm\(|prompt\()",
    r"(?i)(<iframe|<img|<body|<svg)",
    r"(?i)(src=.*javascript:)|(href=.*javascript:)",
]
XSS_COMPILED = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]

def is_sqli_attempt(data):
    """Check if a string contains SQL injection patterns."""
    if not data:
        return False
    for pattern in SQLI_COMPILED:
        if pattern.search(data):
            return True
    return False

def is_xss_attempt(data):
    """Check if a string contains XSS patterns."""
    if not data:
        return False
    for pattern in XSS_COMPILED:
        if pattern.search(data):
            return True
    return False

def scan_request(request):
    """
    Scan request data for attack patterns.
    Returns tuple: (attack_type, severity, description, data_snippet)
    """
    # Combine all user input
    data_to_check = []
    # GET parameters
    for k, v in request.GET.items():
        data_to_check.append(v)
    # POST parameters
    if request.method == 'POST':
        for k, v in request.POST.items():
            data_to_check.append(v)
    # JSON body
    if request.content_type == 'application/json' and request.body:
        try:
            import json
            body = json.loads(request.body)
            data_to_check.append(json.dumps(body))
        except:
            data_to_check.append(request.body.decode('utf-8', errors='ignore'))

    data_str = ' '.join(str(d) for d in data_to_check)

    if is_sqli_attempt(data_str):
        return ('sqli', 3, 'SQL injection pattern detected', data_str[:200])
    if is_xss_attempt(data_str):
        return ('xss', 2, 'Cross‑site scripting pattern detected', data_str[:200])

    # IDOR detection – we'll rely on 403 responses to protected resources
    # We'll handle in middleware by checking if user is authenticated but got 403
    return (None, 0, '', '')

def log_attack(attack_type, severity, description, request, data_snippet=None, blocked=False):
    """Create an AttackLog entry."""
    user = request.user if hasattr(request, 'user') and request.user and request.user.is_authenticated else None
    AttackLog.objects.create(
        attack_type=attack_type,
        severity=severity,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        username=user.username if user else '',
        user_id=user.id if user else None,
        request_path=request.path,
        request_method=request.method,
        request_data=data_snippet or '',
        description=description,
        blocked=blocked,
    )
    # If severity >= 3, notify admins immediately
    if severity >= 3:
        from .tasks import notify_admins_attack
        # Extract only serializable information from request
        request_info = {
            'ip': request.META.get('REMOTE_ADDR'),
            'path': request.path,
            'method': request.method,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'user': request.user.username if hasattr(request, 'user') and request.user and request.user.is_authenticated else 'Anonymous'
        }
        notify_admins_attack.delay(attack_type, severity, description, request_info)

def check_rate_limit(ip, max_requests=100, window_seconds=60):
    """
    Simple rate limiting using Django cache.
    Returns (allowed, requests_count)
    """
    cache_key = f'ratelimit_{ip}'
    requests = cache.get(cache_key, 0)
    if requests >= max_requests:
        return False, requests
    cache.set(cache_key, requests + 1, window_seconds)
    return True, requests + 1