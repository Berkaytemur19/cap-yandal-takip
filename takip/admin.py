"""Admin paneli yalnızca inceleme içindir.

Değişiklikler servis katmanından (takip.services) geçmeli ki işlem kaydına yazılsın;
bu yüzden tüm takip modelleri adminde salt okunurdur.
"""

from django.contrib import admin

from . import models


class SaltOkunurAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Ogrenci)
class OgrenciAdmin(SaltOkunurAdmin):
    list_display = ('ogrenci_no', 'ad', 'soyad', 'program_turu', 'kayit_durumu')
    list_filter = ('program_turu', 'kayit_durumu')
    search_fields = ('ogrenci_no', 'ad', 'soyad')


@admin.register(models.Ders)
class DersAdmin(SaltOkunurAdmin):
    list_display = ('kod', 'ad', 'akts', 'tur', 'aktif')


@admin.register(models.DersDenemesi)
class DersDenemesiAdmin(SaltOkunurAdmin):
    list_display = ('liste_kalemi', 'donem', 'durum', 'harf_notu', 'onay_durumu')
    list_filter = ('onay_durumu', 'durum')


@admin.register(models.IslemKaydi)
class IslemKaydiAdmin(SaltOkunurAdmin):
    list_display = ('zaman', 'kullanici', 'islem', 'model_adi', 'nesne_metni')
    list_filter = ('islem', 'model_adi')


for model in (models.AkademikDonem, models.Protokol, models.ProtokolDersi, models.OgrenciDers,
              models.AnaDalGanoKaydi, models.KuralAyari, models.DersTalebi, models.Belge, models.NotGirisi,
              models.BelgeIstegi, models.Mesaj):
    admin.site.register(model, SaltOkunurAdmin)
