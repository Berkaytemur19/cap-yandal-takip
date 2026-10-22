"""Her sayfada kullanılan bildirim sayıları (menüdeki rozetler)."""

from . import services


def bildirimler(request):
    kullanici = getattr(request, 'user', None)
    if kullanici is None or not kullanici.is_authenticated:
        return {}
    return {'okunmamis_mesaj': services.okunmamis_mesaj_sayisi(kullanici)}
