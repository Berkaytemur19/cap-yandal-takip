"""Rol tabanlı yetki kontrolü. Her view sunucu tarafında bu dekoratörle korunur."""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def istemci_ip(request):
    """django-axes için istemci IP'si.

    Proxy arkasında (PythonAnywhere) gerçek IP'yi X-Real-IP başlığından alır; bu başlığı
    proxy kendisi yazar. Yerelde başlığa güvenilmez, çünkü istemci onu taklit edebilir.
    """
    if settings.PROXY_ARKASINDA and request.META.get('HTTP_X_REAL_IP'):
        return request.META['HTTP_X_REAL_IP']
    return request.META.get('REMOTE_ADDR')


def rol_gerekli(*roller):
    """View'ı yalnızca verilen rollerdeki giriş yapmış kullanıcılara açar.

    Kullanım:
        @rol_gerekli(Rol.KOORDINATOR)
        def ogrenci_ekle(request): ...
    """

    def dekorator(view):
        @wraps(view)
        @login_required
        def sarmal(request, *args, **kwargs):
            if request.user.rol not in roller:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return sarmal

    return dekorator
