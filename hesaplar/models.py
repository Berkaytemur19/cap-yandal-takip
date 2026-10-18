from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    KOORDINATOR = 'KOORDINATOR', 'Koordinatör'
    OGRENCI = 'OGRENCI', 'Öğrenci'
    BOLUM_BASKANI = 'BOLUM_BASKANI', 'Bölüm Başkanı'


class Kullanici(AbstractUser):
    """Sistemdeki tek kullanıcı modeli. Her kullanıcının tam olarak bir rolü vardır.

    Öğrencilerde kullanıcı adı öğrenci numarasıdır. Kendi kendine kayıt yoktur;
    öğrenci hesabını koordinatör açar (takip.services.ogrenci_ekle).
    """

    rol = models.CharField(max_length=20, choices=Rol.choices)

    # createsuperuser komutu rolü de sorsun.
    REQUIRED_FIELDS = ['email', 'rol']

    class Meta:
        verbose_name = 'Kullanıcı'
        verbose_name_plural = 'Kullanıcılar'

    @property
    def koordinator_mu(self):
        return self.rol == Rol.KOORDINATOR

    @property
    def ogrenci_mi(self):
        return self.rol == Rol.OGRENCI

    @property
    def bolum_baskani_mi(self):
        return self.rol == Rol.BOLUM_BASKANI

    def delete(self, *args, **kwargs):
        raise PermissionError('Kullanıcılar silinemez; hesabı pasife alın (is_active=False).')
