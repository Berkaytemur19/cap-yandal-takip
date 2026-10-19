"""Yetkisiz erişimin sunucu tarafında engellendiğini doğrular (URL değiştirme, doğrudan POST)."""

from django.test import TestCase
from django.urls import reverse

from hesaplar.models import Kullanici
from takip.models import Ders, IslemKaydi, Ogrenci

from .yardimci import TestVerisi


class YetkiTest(TestVerisi, TestCase):
    def _koord_sayfalari(self):
        """Yalnızca koordinatöre açık sayfalar."""
        return [
            reverse('ogrenci_ekle'),
            reverse('ders_katalogu'),
            reverse('ders_duzenle', args=[self.ders1.pk]),
        ]

    def _yonetim_sayfalari(self):
        """Koordinatör ve bölüm başkanına açık sayfalar."""
        return [
            reverse('ogrenci_listesi'),
            reverse('ogrenci_detay', args=[self.ogrenci_a.pk]),
            reverse('ogrenci_detay', args=[self.ogrenci_b.pk]),
            reverse('islem_gecmisi'),
        ]

    def _yasakli_postlar(self):
        """Veriyi değiştiren istekler; başkan ve öğrenci için hepsi 403 olmalı."""
        return [
            (reverse('ders_katalogu'), {'kod': '9999999', 'ad': 'Sızma', 'akts': 4, 'tur': 'ZORUNLU'}),
            (reverse('ders_duzenle', args=[self.ders1.pk]),
             {'kod': self.ders1.kod, 'ad': 'Değiştirildi', 'akts': 9, 'tur': 'ZORUNLU'}),
            (reverse('ders_aktiflik', args=[self.ders1.pk]), {'aktif': '0'}),
            (reverse('ogrenci_ekle'), {
                'ogrenci_no': '20259999', 'ad': 'Sızma', 'soyad': 'Deneme',
                'okul_eposta': '20259999@ogr.example.edu.tr', 'program_turu': 'CAP',
                'ana_dal_bolumu': 'Elektrik-Elektronik Müh.', 'protokol': self.protokol.pk,
                'kabul_yili': 2026, 'kabul_donemi': 'GUZ',
            }),
        ]

    def _veri_degismedi(self, islem_sayisi):
        self.assertFalse(Ders.objects.filter(kod='9999999').exists())
        self.assertFalse(Ogrenci.objects.filter(ogrenci_no='20259999').exists())
        self.ders1.refresh_from_db()
        self.assertEqual((self.ders1.ad, self.ders1.akts, self.ders1.aktif),
                         ('Bilgisayar Mühendisliğine Giriş', 4, True))
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)

    # --- Giriş yapmamış ziyaretçi ---------------------------------------------

    def test_anonim_giris_sayfasina_yonlenir(self):
        for url in [reverse('benim'), *self._koord_sayfalari(), *self._yonetim_sayfalari()]:
            cevap = self.client.get(url)
            self.assertRedirects(cevap, f"{reverse('giris')}?next={url}", msg_prefix=url)

    def test_anonim_post_veri_degistiremez(self):
        islem_sayisi = IslemKaydi.objects.count()
        for url, veri in self._yasakli_postlar():
            self.assertEqual(self.client.post(url, veri).status_code, 302, url)
        self._veri_degismedi(islem_sayisi)

    # --- Öğrenci -----------------------------------------------------------

    def test_ogrenci_baskasinin_kaydini_acamaz(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        cevap = self.client.get(reverse('ogrenci_detay', args=[self.ogrenci_b.pk]))
        self.assertEqual(cevap.status_code, 403)
        self.assertNotContains(cevap, 'Mehmet', status_code=403)

    def test_ogrenci_yonetim_sayfalarini_acamaz(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        for url in [*self._koord_sayfalari(), *self._yonetim_sayfalari()]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_ogrenci_sayfasi_yalnizca_kendi_kaydini_gosterir(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        cevap = self.client.get(reverse('benim'))
        self.assertContains(cevap, 'Ayşe')
        self.assertNotContains(cevap, 'Mehmet')

    def test_ogrenci_post_veri_degistiremez(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        islem_sayisi = IslemKaydi.objects.count()
        for url, veri in self._yasakli_postlar():
            self.assertEqual(self.client.post(url, veri).status_code, 403, url)
        self._veri_degismedi(islem_sayisi)

    # --- Bölüm başkanı (salt okunur) -----------------------------------------

    def test_baskan_koordinator_sayfalarini_acamaz(self):
        self.client.force_login(self.baskan)
        for url in self._koord_sayfalari():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_baskan_post_veri_degistiremez(self):
        self.client.force_login(self.baskan)
        islem_sayisi = IslemKaydi.objects.count()
        for url, veri in self._yasakli_postlar():
            self.assertEqual(self.client.post(url, veri).status_code, 403, url)
        self._veri_degismedi(islem_sayisi)

    # --- Diğer durumlar -------------------------------------------------------

    def test_ogrenci_sayfasi_yalnizca_ogrenciye_acik(self):
        for kullanici in (self.koordinator, self.baskan):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('benim')).status_code, 403, kullanici.username)

    def test_rolsuz_hesap_hicbir_sey_goremez(self):
        rolsuz = Kullanici.objects.create_user('rolsuz', password='Test.12345', rol='')
        self.client.force_login(rolsuz)
        for url in [reverse('ana_sayfa'), reverse('benim'), *self._koord_sayfalari(), *self._yonetim_sayfalari()]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_aktiflik_degisikligi_get_ile_yapilamaz(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.get(reverse('ders_aktiflik', args=[self.ders1.pk]), {'aktif': '0'})
        self.assertEqual(cevap.status_code, 405)
        self.ders1.refresh_from_db()
        self.assertTrue(self.ders1.aktif)
