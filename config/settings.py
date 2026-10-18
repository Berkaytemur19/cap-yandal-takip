"""
ÇAP / Yandal Takip Sistemi — Django ayarları.

Geliştirme ortamı içindir. Gizli anahtar ortam değişkeninden okunur;
tanımlı değilse yalnızca yerel geliştirme için bir varsayılan kullanılır.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-sadece-yerel-gelistirme-icin-degistirin',
)
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'hesaplar',
    'takip',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # axes en sonda olmalı: başarısız giriş denemelerini sayar ve kilitler.
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# --- Kimlik doğrulama ---
AUTH_USER_MODEL = 'hesaplar.Kullanici'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',  # önce axes: kilitli mi?
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'giris'
LOGIN_REDIRECT_URL = 'ana_sayfa'
LOGOUT_REDIRECT_URL = 'giris'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# django-axes: 5 hatalı denemede kullanıcı+IP 30 dakika kilitlenir.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5  # saat
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'hesaplar/kilitli.html'


# --- Dil ve saat ---
LANGUAGE_CODE = 'tr'
TIME_ZONE = 'Europe/Istanbul'
USE_I18N = True
USE_TZ = True


# --- Statik dosyalar ---
STATIC_URL = 'static/'

# Yüklenen belgeler web kökü dışında tutulacak (sonraki oturum).
# MEDIA_URL bilerek tanımlanmıyor: dosyalar yalnızca yetki kontrollü view ile sunulacak.
KORUMALI_DOSYA_KOKU = BASE_DIR / 'korumali_dosyalar'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
