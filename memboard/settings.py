import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']

APP_URL = os.environ.get('APP_URL', 'http://localhost:8000')
CSRF_TRUSTED_ORIGINS = [APP_URL] if APP_URL.startswith('https') else []

# Only force HTTPS when APP_URL is actually https — keeps local dev
# (http://localhost:8000, no cert) working without a separate flag.
if APP_URL.startswith('https'):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'core.middleware.ProfileLanguageMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'memboard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'core.context_processors.sidebar_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'memboard.wsgi.application'

# Database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

# Languages WorthKeeping has translations for — add a new (code, "Native name")
# pair here once its locale/<code>/LC_MESSAGES/django.po is translated.
LANGUAGES = [
    ('en', 'English'),
    ('el', 'Ελληνικά'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# Static files
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media / Cloudflare R2
USE_R2 = os.environ.get('USE_R2', 'False') == 'True'

if USE_R2:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID       = os.environ.get('R2_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY   = os.environ.get('R2_SECRET_ACCESS_KEY', '')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', '')
    AWS_S3_ENDPOINT_URL     = os.environ.get('R2_ENDPOINT_URL', '')
    AWS_S3_CUSTOM_DOMAIN    = os.environ.get('R2_PUBLIC_DOMAIN', '')
    AWS_DEFAULT_ACL         = None
    AWS_S3_FILE_OVERWRITE   = False
    AWS_QUERYSTRING_AUTH    = False
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = 'https://{}/'.format(AWS_S3_CUSTOM_DOMAIN)
    else:
        MEDIA_URL = '{}/{}/'.format(AWS_S3_ENDPOINT_URL, AWS_STORAGE_BUCKET_NAME)
else:
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/'
LOGOUT_REDIRECT_URL = '/login/'

# Rate limiting (django-ratelimit) — in production, gunicorn is reached
# through a Unix socket behind nginx, so REMOTE_ADDR is empty. nginx's
# default proxy_params sets X-Real-IP to the real client address, so read
# the visitor's IP from there instead. Only do this when actually running
# behind that proxy (DATABASE_URL is only set in production) — locally,
# runserver populates REMOTE_ADDR itself and there's no X-Real-IP header.
if DATABASE_URL:
    RATELIMIT_IP_META_KEY = 'HTTP_X_REAL_IP'

# Email — sent via the Resend HTTP API rather than SMTP, since our host
# blocks outbound SMTP ports (see core/email_backends.py for why).
EMAIL_BACKEND      = 'core.email_backends.ResendEmailBackend'
RESEND_API_KEY     = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_EMAIL  = os.environ.get('RESEND_FROM_EMAIL', 'onboarding@resend.dev')
DEFAULT_FROM_EMAIL = RESEND_FROM_EMAIL
# Kept only for VAPID_ADMIN_EMAIL below (unused elsewhere) — harmless if unset.
EMAIL_HOST_USER    = os.environ.get('EMAIL_HOST_USER', '')

# Where "Report a problem" messages from the sidebar get sent.
REPORT_PROBLEM_EMAIL = os.environ.get('REPORT_PROBLEM_EMAIL', 'memory.board.26@gmail.com')

# Password reset
PASSWORD_RESET_TIMEOUT = 86400

# Push notifications (VAPID)
VAPID_PUBLIC_KEY  = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_ADMIN_EMAIL = os.environ.get('EMAIL_HOST_USER', '')

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
