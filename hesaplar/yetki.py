"""Rol tabanlı yetki kontrolü. Her view sunucu tarafında bu dekoratörle korunur."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


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
