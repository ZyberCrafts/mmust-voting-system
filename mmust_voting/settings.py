# mmust_voting/settings.py

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-this-in-production')

# Development mode: set DEBUG=True explicitly in .env
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Allowed hosts
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.yourdomain.com',  # Change to your domain
    '.ngrok.io',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'voting',
    'chatbot',
    'ml',
    'security',
    'accountability',
    'channels',
    'django_otp',
    'django_otp.plugins.otp_totp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'security.middleware.SecurityMiddleware',          
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mmust_voting.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'voting.context_processors.active_election',
                'voting.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'mmust_voting.wsgi.application'
ASGI_APPLICATION = 'mmust_voting.asgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'mmust_voting'),
        'USER': os.environ.get('DB_USER', 'mmust_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'ZyberCrafts-01.com'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

AUTH_USER_MODEL = 'voting.User'

AUTH_PASSWORD_VALIDATORS = [
    #{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')      # environment variable name
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@mmust.ac.ke')

# SMS
SMS_API_KEY = os.environ.get('SMS_API_KEY')
SMS_USERNAME = os.environ.get('SMS_USERNAME')

# Portal API
MMUST_PORTAL_API_URL = os.environ.get('MMUST_PORTAL_API_URL')
MMUST_PORTAL_API_KEY = os.environ.get('MMUST_PORTAL_API_KEY')

CONTACT_EMAIL = 'festusonwonga@gmail.com'  # email where contact messages go
DEFAULT_FROM_EMAIL = 'noreply@mmust.ac.ke'
# Election master passphrase
ELECTION_MASTER_PASSPHRASE = os.environ.get('ELECTION_MASTER_PASSPHRASE', 'change-me')

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULE = {
    'check-ended-elections': {
        'task': 'voting.tasks.check_ended_elections',
        'schedule': 60.0,  # every 60 seconds
    },
}

# WebPush
WEBPUSH_SETTINGS = {
    'VAPID_PUBLIC_KEY': os.environ.get('VAPID_PUBLIC_KEY', 'your-public-key'),
    'VAPID_PRIVATE_KEY': os.environ.get('VAPID_PRIVATE_KEY', 'your-private-key'),
    'VAPID_ADMIN_EMAIL': os.environ.get('VAPID_ADMIN_EMAIL', 'admin@mmust.ac.ke')
}

# Channels layer (Redis)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [CELERY_BROKER_URL],
        },
    },
}

# Logging
LOG_DIR = BASE_DIR / 'logs'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = '/login/' 

if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'errors.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': True,
        },
        'voting': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
# ==========================================================
# SECURITY SETTINGS – EXPLICITLY DISABLE SSL IN DEVELOPMENT
# ==========================================================
if DEBUG:
    # Development: No HTTPS, no HSTS
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
else:
    # Production: Enable HTTPS and HSTS
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# OpenAI
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')  # or gpt-4
SITE_NAME = "MMUST Voting System"
SITE_LOGO = "/static/images/mmust_logo.png"   # adjust path

# AI/ML features (disabled by default)
AI_ENABLED_FEATURES = [
    # 'face_deep',
    # 'manifesto_analysis',
    # 'feedback_sentiment',
    # 'anomaly_detection',
    # 'predictive_analytics',
]

# You can later install required packages:
# python manage.py run_ai_analysis