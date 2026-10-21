"""Onay bekleyenler ekranı: onaylama, gerekçeli ret ve yetkisiz erişim."""

from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.models import DenemeDurumu, IslemKaydi, OnayDurumu

from .yardimci import TestVerisi


class OnayEkraniTest(TestVerisi, TestCase):
    def setUp(self):
        kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)
        self.deneme = services.deneme_ekle(self.ogrenci_a.kullanici, kalem, self.donem, DenemeDurumu.ALINDI)

    def _onay_durumu(self):
        self.deneme.refresh_from_db()
        return self.deneme.onay_durumu

    def test_liste_bekleyen_kaydi_gosterir(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.get(reverse('onay_bekleyenler'))
        self.assertContains(cevap, '1001')
        self.assertContains(cevap, self.ders1.kod)
        self.assertContains(cevap, reverse('deneme_onayla', args=[self.deneme.pk]))

    def test_koordinator_onaylar(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('deneme_onayla', args=[self.deneme.pk]), follow=True)
        self.assertRedirects(cevap, reverse('onay_bekleyenler'))
        self.assertContains(cevap, 'onaylandı')
        self.assertEqual(self._onay_durumu(), OnayDurumu.ONAYLANDI)
        self.assertEqual(self.deneme.onaylayan, self.koordinator)
        self.assertTrue(IslemKaydi.objects.filter(islem='deneme_onayla', nesne_id=str(self.deneme.pk)).exists())
        # Onaylanan kayıt listeden düşer.
        self.assertContains(cevap, 'Onay bekleyen kayıt yok.')

    def test_koordinator_gerekceyle_reddeder(self):
        self.client.force_login(self.koordinator)
        self.client.post(reverse('deneme_reddet', args=[self.deneme.pk]), {'gerekce': 'Yanlış dönem seçilmiş'})
        self.assertEqual(self._onay_durumu(), OnayDurumu.REDDEDILDI)
        self.assertEqual(self.deneme.red_gerekcesi, 'Yanlış dönem seçilmiş')

    def test_gerekcesiz_ret_yapilamaz(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('deneme_reddet', args=[self.deneme.pk]), {'gerekce': '   '}, follow=True)
        self.assertContains(cevap, 'Gerekçe yazılması zorunludur.')
        self.assertEqual(self._onay_durumu(), OnayDurumu.BEKLIYOR)

    def test_onaylanmis_kayit_tekrar_onaylanamaz(self):
        self.client.force_login(self.koordinator)
        url = reverse('deneme_onayla', args=[self.deneme.pk])
        self.client.post(url)
        islem_sayisi = IslemKaydi.objects.count()
        cevap = self.client.post(url, follow=True)
        self.assertContains(cevap, 'Yalnızca onay bekleyen kayıt onaylanabilir.')
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)

    def test_get_ile_onaylanamaz(self):
        self.client.force_login(self.koordinator)
        self.assertEqual(self.client.get(reverse('deneme_onayla', args=[self.deneme.pk])).status_code, 405)
        self.assertEqual(self._onay_durumu(), OnayDurumu.BEKLIYOR)

    def test_baskan_ve_ogrenci_onaylayamaz_reddedemez(self):
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogrenci_a.kullanici, self.ogrenci_b.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('onay_bekleyenler')).status_code, 403)
            self.assertEqual(self.client.post(reverse('deneme_onayla', args=[self.deneme.pk])).status_code, 403)
            cevap = self.client.post(reverse('deneme_reddet', args=[self.deneme.pk]), {'gerekce': 'x'})
            self.assertEqual(cevap.status_code, 403)
        self.assertEqual(self._onay_durumu(), OnayDurumu.BEKLIYOR)
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
