"""
Django settings for the Pets Central store operations system.

All environment-specific values come from environment variables. Locally they
are loaded from `.env`; in Azure they come from the container's environment and Key Vault.

https://docs.djangoproject.com/en/6.1/topics/settings/
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

DEBUG = env_bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'stores',
    'catalog',
    'customers',
    'inventory',
    'sales',
    'datagen',
    'policies',
    'storefront',
    'assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves the collected static files from the app itself, so the container needs no web server in front.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'storefront.middleware.CurrentStoreMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'storefront.context_processors.storefront',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['POSTGRES_DB'],
        'USER': os.environ['POSTGRES_USER'],
        'PASSWORD': os.environ['POSTGRES_PASSWORD'],
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        # Azure Database for PostgreSQL Flexible Server requires 'require'.
        'OPTIONS': {'sslmode': os.environ.get('POSTGRES_SSLMODE', 'prefer')},
        'CONN_MAX_AGE': 60,
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}


# Behind HTTPS in Azure: the ingress terminates TLS and says so in X-Forwarded-Proto.

if env_bool('DJANGO_HTTPS', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]


# Sign-in

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'
# Shows the demo sign-in map, where picking a store fills in its manager's login. Off unless asked for.
DEMO_SIGN_IN = env_bool('DJANGO_DEMO_SIGN_IN', default=False)
# The password demo store managers sign in with. The login form fills it in after a store is picked on the map.
DEMO_PASSWORD = os.environ.get('DJANGO_DEMO_PASSWORD', '')


# Store Assistant
# Claude answers a manager's questions from their store's data (SQL run as a read-only login that sees one store)
# and from the company's policies (pgvector search, where the database has the extension).

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ASSISTANT_MODEL = os.environ.get('ASSISTANT_MODEL', 'claude-opus-5-5')
ASSISTANT_DB_USER = os.environ.get('ASSISTANT_DB_USER', 'pets_assistant')
ASSISTANT_DB_PASSWORD = os.environ.get('ASSISTANT_DB_PASSWORD', '')
# Questions one person can ask a day, to keep the API bill bounded.
ASSISTANT_DAILY_LIMIT = int(os.environ.get('ASSISTANT_DAILY_LIMIT', '40'))
# Questions everyone together can ask a day; 0 means no such limit. The demo sets it, since its visitors share
# store manager accounts and the API key has no spend limit.
ASSISTANT_SITE_DAILY_LIMIT = int(os.environ.get('ASSISTANT_SITE_DAILY_LIMIT', '0'))
# Policy search's embeddings: an Azure OpenAI deployment, reached with the app's managed identity, so no key exists.
# Unset locally, where Postgres has no pgvector anyway.
AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT', '')
POLICY_EMBEDDING_DEPLOYMENT = os.environ.get('POLICY_EMBEDDING_DEPLOYMENT', 'text-embedding-3-small')
