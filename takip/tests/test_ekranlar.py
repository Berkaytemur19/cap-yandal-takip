"""Ekranların her rol için açıldığını ve temel akışların çalıştığını doğrular."""

from django.test import TestCase
from django.urls import reverse

from takip.models import Ders, IslemKaydi, Ogrenci

from .yardimci import TestVerisi

SIFRE = 'Test.12345'


class EkranTest(TestVerisi, TestCase):
    def test_giris_sayfasi_ve_yonlendirme(self):
        self.assertEqual(self.client.get(reverse('giris')).status_code, 200)
        cevap = self.client.get(reverse('ana_sayfa'))
        self.assertRedirects(cevap, reverse('giris') + '?next=/')

    def test_giris_rol_yonlendirmesi(self):
        cevap = self.client.post(reverse('giris'), {'username': '1001', 'password': SIFRE}, follow=True)
        self.assertEqual(cevap.redirect_chain[-1][0], reverse('benim'))
        self.assertContains(cevap, 'Ayşe Test')

    def test_koordinator_sayfalari(self):
        self.client.force_login(self.koordinator)
        for ad in ('ana_sayfa', 'ogrenci_listesi', 'ogrenci_ekle', 'ders_katalogu', 'islem_gecmisi'):
            self.assertEqual(self.client.get(reverse(ad)).status_code, 200, ad)
        cevap = self.client.get(reverse('ogrenci_detay', args=[self.ogrenci_a.pk]))
        self.assertContains(cevap, '3301156')

    def test_baskan_sayfalari(self):
        self.client.force_login(self.baskan)
        for ad in ('ana_sayfa', 'ogrenci_listesi', 'islem_gecmisi'):
            self.assertEqual(self.client.get(reverse(ad)).status_code, 200, ad)
        cevap = self.client.get(reverse('ogrenci_listesi'))
        self.assertNotContains(cevap, 'Öğrenci ekle')

    def test_ogrenci_ekleme_ekrani_hesap_acar(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('ogrenci_ekle'), {
            'ogrenci_no': '20250001', 'ad': 'Yeni', 'soyad': 'Öğrenci',
            'okul_eposta': '20250001@ogr.example.edu.tr', 'program_turu': 'CAP',
            'ana_dal_bolumu': 'Elektrik-Elektronik Müh.', 'protokol': self.protokol.pk,
            'kabul_yili': 2026, 'kabul_donemi': 'GUZ',
        })
        self.assertContains(cevap, 'Geçici şifre')
        ogrenci = Ogrenci.objects.get(ogrenci_no='20250001')
        self.assertEqual(ogrenci.kabul_donemi.baslangic_yili, 2026)
        self.assertTrue(ogrenci.kullanici.has_usable_password())

    def test_katalog_ekle_duzenle_pasife_al(self):
        self.client.force_login(self.koordinator)
        self.client.post(reverse('ders_katalogu'), {'kod': '3301455', 'ad': 'Yazılım Müh.', 'akts': 4, 'tur': 'ZORUNLU'})
        ders = Ders.objects.get(kod='3301455')
        self.client.post(reverse('ders_duzenle', args=[ders.pk]),
                         {'kod': 'DEGISMEZ', 'ad': 'Yazılım Mühendisliği', 'akts': 4, 'tur': 'ZORUNLU'})
        self.client.post(reverse('ders_aktiflik', args=[ders.pk]), {'aktif': '0'})
        ders.refresh_from_db()
        self.assertEqual((ders.kod, ders.ad, ders.aktif), ('3301455', 'Yazılım Mühendisliği', False))
        self.assertTrue(IslemKaydi.objects.filter(islem='katalog_ders_pasif', nesne_id=str(ders.pk)).exists())
