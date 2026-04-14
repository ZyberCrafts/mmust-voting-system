# voting/portal_api.py

import requests
import logging
from functools import lru_cache
from django.conf import settings
import time

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Retry decorator (exponential backoff)
# ------------------------------------------------------------------
def retry(max_retries=3, backoff_factor=1):
    """Retry a function with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        logger.error(f"Max retries reached: {e}")
                        raise
                    wait = backoff_factor * (2 ** (retries - 1))
                    logger.warning(f"Retry {retries}/{max_retries} after {wait}s: {e}")
                    time.sleep(wait)
            return None
        return wrapper
    return decorator

# ------------------------------------------------------------------
# Caching decorator (in-memory, per admission number)
# ------------------------------------------------------------------
def cache_result(maxsize=128):
    """Simple in-memory cache using lru_cache."""
    def decorator(func):
        cached_func = lru_cache(maxsize=maxsize)(func)
        def wrapper(admission_number):
            return cached_func(admission_number)
        return wrapper
    return decorator

# ------------------------------------------------------------------
# Mock data for development (when no API configured)
# ------------------------------------------------------------------
def get_mock_status(admission_number):
    """Return mock data for development."""
    # In real app, you could simulate different cases
    if admission_number.startswith('SCI/'):
        return {
            'missing_marks': False,
            'supplementary_exams': False,
            'name': 'John Doe',
            'course': 'Computer Science',
        }
    elif admission_number.startswith('EDU/'):
        return {
            'missing_marks': True,
            'supplementary_exams': False,
            'name': 'Jane Smith',
            'course': 'Education',
        }
    else:
        return {
            'missing_marks': False,
            'supplementary_exams': True,
            'name': 'Unknown',
            'course': 'Unknown',
        }

# ------------------------------------------------------------------
# Core API call with retry and caching
# ------------------------------------------------------------------
@retry(max_retries=3, backoff_factor=1)
@cache_result(maxsize=256)
def fetch_student_academic_status(admission_number):
    """
    Query MMUST portal Heroku app for student academic status.
    Returns dict with keys: missing_marks, supplementary_exams, name, course.
    Returns None on failure (after retries).
    """
    url = settings.MMUST_PORTAL_API_URL
    api_key = settings.MMUST_PORTAL_API_KEY
    timeout = getattr(settings, 'MMUST_PORTAL_API_TIMEOUT', 10)

    # If no API configured, use mock data (only in development)
    if not url or not api_key:
        if settings.DEBUG:
            logger.warning("Portal API not configured, using mock data.")
            return get_mock_status(admission_number)
        else:
            logger.error("Portal API not configured in production.")
            return None

    try:
        response = requests.post(
            url,
            json={'admission': admission_number},
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            return {
                'missing_marks': data.get('missing_marks', False),
                'supplementary_exams': data.get('supplementary_exams', False),
                'name': data.get('name', ''),
                'course': data.get('course', ''),
            }
        else:
            logger.error(f"Portal API error: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Portal API timeout after {timeout}s")
        raise  # let retry handle
    except Exception as e:
        logger.error(f"Portal API request failed: {e}")
        raise  # let retry handle

# ------------------------------------------------------------------
# Optional: Fetch candidate details (extended)
# ------------------------------------------------------------------
def fetch_student_academic_status(admission_number):
    """
    Query MMUST portal Heroku app for student academic status.
    Returns None on failure (network, timeout, invalid URL).
    """
    url = settings.MMUST_PORTAL_API_URL
    api_key = settings.MMUST_PORTAL_API_KEY
    timeout = getattr(settings, 'MMUST_PORTAL_API_TIMEOUT', 10)

    # If no API configured or DEBUG=True, skip real call (optional)
    if not url or not api_key or settings.DEBUG:
        if settings.DEBUG:
            logger.warning("Portal API not configured or DEBUG=True – skipping eligibility check.")
        return None

    try:
        response = requests.post(
            url,
            json={'admission': admission_number},
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            return {
                'missing_marks': data.get('missing_marks', False),
                'supplementary_exams': data.get('supplementary_exams', False),
                'name': data.get('name', ''),
                'course': data.get('course', ''),
            }
        else:
            logger.error(f"Portal API error: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Portal API connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"Portal API request failed: {e}")
        return None