"""
ÇAP / Yandal Takip Sistemi — Django ayarları.

Ayarlar ortam değişkenlerinden okunur; proje kökünde bir `.env` dosyası varsa
önce o yüklenir (örnek: `.env.ornek`). `.env` yoksa yerel geliştirme varsayılanları
kullanılır. Canlı sunucuda DJANGO_DEBUG=0 ve gerçek bir DJANGO_SECRET_KEY zorunludur.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

YEREL_ANAHTAR = 'django-insecure-sadece-yerel-gelistirme-icin-degistirin'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', YEREL_ANAHTAR)
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
if not DEBUG and SECRET_KEY == YEREL_ANAHTAR:
    raise ImproperlyConfigured('DEBUG kapalıyken DJANGO_SECRET_KEY tanımlanmalı.')

# Virgülle ayrılmış alan adları, örn: kullaniciadi.pythonanywhere.com
ALLOWED_HOSTS = ['127.0.0.1', 'localhost'] + [
    h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()
]
CSRF_TRUSTED_ORIGINS = [f'https://{h}' for h in ALLOWED_HOSTS if h not in ('127.0.0.1', 'localhost')]

# Canlı sunucu (PythonAnywhere) bir vekil sunucunun (proxy) arkasında çalışır:
# HTTPS bilgisi ve gerçek istemci IP'si başlıklarla gelir.
PROXY_ARKASINDA = os.environ.get('DJANGO_PROXY_ARKASINDA', '0') == '1'
if PROXY_ARKASINDA:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = PROXY_ARKASINDA  # http:// istekleri https://'e yönlendirilir
    SECURE_HSTS_SECONDS = 3600
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'


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
# Proxy arkasında REMOTE_ADDR herkes için aynı olur; gerçek IP X-Real-IP başlığındadır.
AXES_CLIENT_IP_CALLABLE = 'hesaplar.yetki.istemci_ip'


# --- Dil ve saat ---
LANGUAGE_CODE = 'tr'
TIME_ZONE = 'Europe/Istanbul'
USE_I18N = True
USE_TZ = True


# --- Statik dosyalar ---
STATIC_URL = 'static/'
# `manage.py collectstatic` dosyaları buraya toplar; canlı sunucu /static/ adresini bu klasöre bağlar.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Yüklenen belgeler web kökü dışında tutulur.
# MEDIA_URL bilerek tanımlanmıyor: dosyalar yalnızca yetki kontrollü view (belge_dosyasi) ile sunulur.
KORUMALI_DOSYA_KOKU = BASE_DIR / 'korumali_dosyalar'

# Belge yükleme sınırları. Tür, dosya uzantısına değil içeriğine bakılarak (python-magic) belirlenir.
BELGE_AZAMI_BOYUT = 5 * 1024 * 1024  # 5 MB
BELGE_IZINLI_TURLER = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
