"""Testlerde ortak kullanılan veri kurulumu."""

from hesaplar.models import Kullanici, Rol
from takip import services
from takip.models import DonemTuru, ProgramTuru


class TestVerisi:
    @classmethod
    def setUpTestData(cls):
        cls.koordinator = Kullanici.objects.create_user('koord', password='Test.12345', rol=Rol.KOORDINATOR)
        cls.baskan = Kullanici.objects.create_user('baskan', password='Test.12345', rol=Rol.BOLUM_BASKANI)
        k = cls.koordinator
        cls.donem = services.donem_bul_veya_ekle(k, 2025, DonemTuru.GUZ)
        cls.donem2 = services.donem_bul_veya_ekle(k, 2025, DonemTuru.BAHAR)
        cls.ders1 = services.katalog_dersi_ekle(k, '3301156', 'Bilgisayar Mühendisliğine Giriş', 4, 'ZORUNLU')
        cls.ders2 = services.katalog_dersi_ekle(k, '3301354', 'Veri Yapıları ve Uygulamaları', 4, 'ZORUNLU')
        cls.protokol = services.protokol_ekle(
            k, 'Test ÇAP', ProgramTuru.CAP, 'Elektrik-Elektronik Müh.', [(cls.ders1, 1), (cls.ders2, 3)],
        )
        cls.ogrenci_a, _ = services.ogrenci_ekle(
            k, ogrenci_no='1001', ad='Ayşe', soyad='Test', okul_eposta='1001@ogr.example.edu.tr',
            program_turu=ProgramTuru.CAP, ana_dal_bolumu='Elektrik-Elektronik Müh.',
            protokol=cls.protokol, kabul_donemi=cls.donem, sifre='Test.12345',
        )
        cls.ogrenci_b, _ = services.ogrenci_ekle(
            k, ogrenci_no='1002', ad='Mehmet', soyad='Test', okul_eposta='1002@ogr.example.edu.tr',
            program_turu=ProgramTuru.CAP, ana_dal_bolumu='Elektrik-Elektronik Müh.',
            protokol=cls.protokol, kabul_donemi=cls.donem, sifre='Test.12345',
        )
