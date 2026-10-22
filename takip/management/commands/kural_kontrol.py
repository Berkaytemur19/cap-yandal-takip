"""Tüm öğrencileri güncel kural ayarlarıyla kontrol eder.

Ders, not ve GANO değişince kontrol zaten kendiliğinden yapılır. Bu komut tarihe bağlı kurallar
(ders almama, azami süre) içindir; günde bir kez çalıştırılabilir (ör. PythonAnywhere "Tasks"):
    python manage.py kural_kontrol
"""

from django.core.management.base import BaseCommand

from takip import services
from takip.models import KuralUyarisi


class Command(BaseCommand):
    help = 'Tüm öğrencileri güncel kural ayarlarıyla kontrol eder (tarihe bağlı kurallar için günlük).'

    def handle(self, *args, **options):
        sayi = services.tum_ogrencileri_kontrol_et()
        acik = KuralUyarisi.objects.filter(kapanma_tarihi__isnull=True).count()
        self.stdout.write(self.style.SUCCESS(f'{sayi} öğrenci kontrol edildi; açık uyarı sayısı: {acik}.'))
