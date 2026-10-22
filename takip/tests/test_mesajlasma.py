"""Mesajlaşma, ek belge isteği ve koordinatörün belge yüklemesi."""

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.models import (
    Belge, BelgeDurumu, BelgeIstegi, BelgeTuru, IslemKaydi, Mesaj, MesajDegistirilemez, SilmeYasak,
)

from .test_belgeler import EXE, GeciciDepo, dosya
from .yardimci import TestVerisi


class MesajServisTest(GeciciDepo, TestVerisi, TestCase):
    def setUp(self):
        super().setUp()
        self.ogr = self.ogrenci_a.kullanici

    def test_ogrenci_yalnizca_kendi_yazismasina_yazar(self):
        mesaj = services.mesaj_gonder(self.ogr, 'Merhaba hocam', ogrenci=self.ogrenci_b)
        self.assertEqual(mesaj.ogrenci, self.ogrenci_a)
        self.assertTrue(IslemKaydi.objects.filter(islem='mesaj_gonder', nesne_id=str(mesaj.pk)).exists())

    def test_koordinator_yazar_baskan_yazamaz(self):
        mesaj = services.mesaj_gonder(self.koordinator, 'Formunuz eksik', ogrenci=self.ogrenci_a)
        self.assertEqual((mesaj.ogrenci, mesaj.gonderen), (self.ogrenci_a, self.koordinator))
        with self.assertRaises(PermissionDenied):
            services.mesaj_gonder(self.baskan, 'x', ogrenci=self.ogrenci_a)

    def test_bos_ve_cok_uzun_mesaj_gonderilemez(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'boş olamaz'):
            services.mesaj_gonder(self.ogr, '   ')
        with self.assertRaisesMessage(services.IslemHatasi, 'en fazla'):
            services.mesaj_gonder(self.ogr, 'a' * 5001)
        self.assertFalse(Mesaj.objects.exists())

    def test_mesaj_degistirilemez_ve_silinemez(self):
        mesaj = services.mesaj_gonder(self.ogr, 'İlk hâli')
        mesaj.metin = 'Değiştirilmiş'
        with self.assertRaises(MesajDegistirilemez):
            mesaj.save()
        with self.assertRaises(SilmeYasak):
            Mesaj.objects.get(pk=mesaj.pk).delete()
        with self.assertRaises(SilmeYasak):
            Mesaj.objects.all().delete()
        self.assertEqual(Mesaj.objects.get(pk=mesaj.pk).metin, 'İlk hâli')

    def test_ek_dosya_kontrol_edilir(self):
        mesaj = services.mesaj_gonder(self.ogr, 'Ekte form', dosya('form.pdf'))
        self.assertEqual((mesaj.ek_adi, mesaj.ek_mime), ('form.pdf', 'application/pdf'))
        self.assertTrue((self.depo_koku / mesaj.ek_yolu).is_file())
        with self.assertRaisesMessage(services.IslemHatasi, 'Yalnızca PDF, JPG veya PNG'):
            services.mesaj_gonder(self.ogr, 'Zararlı', dosya('virus.pdf', EXE))
        self.assertEqual(Mesaj.objects.count(), 1)
        self.assertEqual(len(self.diskteki_dosyalar()), 1)

    def test_okunmamis_sayisi_ve_okundu_isareti(self):
        services.mesaj_gonder(self.ogr, 'Soru 1')
        services.mesaj_gonder(self.ogr, 'Soru 2')
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.koordinator), 2)
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.ogr), 0)  # kendi mesajı bildirim değil
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.baskan), 0)
        services.mesajlari_okundu_isaretle(self.koordinator, self.ogrenci_a)
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.koordinator), 0)
        services.mesaj_gonder(self.koordinator, 'Yanıt', ogrenci=self.ogrenci_a)
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.ogr), 1)
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.ogrenci_b.kullanici), 0)


class BelgeIstegiServisTest(GeciciDepo, TestVerisi, TestCase):
    def setUp(self):
        super().setUp()
        self.ogr = self.ogrenci_a.kullanici
        self.istek = services.belge_iste(self.koordinator, self.ogrenci_a, BelgeTuru.DIGER,
                                         'Özel şartlı ders muafiyet formu')

    def test_istek_yazismaya_duser_ve_bekliyor_baslar(self):
        self.assertEqual(self.istek.durum[0], 'BEKLIYOR')
        mesaj = Mesaj.objects.get(istek=self.istek)
        self.assertEqual(mesaj.ogrenci, self.ogrenci_a)
        self.assertIn('Özel şartlı ders muafiyet formu', mesaj.metin)
        self.assertEqual(services.okunmamis_mesaj_sayisi(self.ogr), 1)

    def test_yanit_yuklenir_onaylanir(self):
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya(), istek=self.istek)
        self.istek.refresh_from_db()
        self.assertEqual(belge.tur, BelgeTuru.DIGER)  # tür istekten gelir
        self.assertEqual((self.istek.belge, self.istek.durum[0]), (belge, 'YUKLENDI'))
        with self.assertRaisesMessage(services.IslemHatasi, 'zaten belge yüklendi'):
            services.belge_yukle(self.ogr, BelgeTuru.DIGER, dosya(), istek=self.istek)
        services.belge_onayla(self.koordinator, belge)
        self.istek.refresh_from_db()
        self.assertEqual(self.istek.durum[0], 'ONAYLANDI')

    def test_reddedilirse_yeni_surum_yuklenir_eskisi_kalir(self):
        ilk = services.belge_yukle(self.ogr, BelgeTuru.DIGER, dosya(), istek=self.istek)
        services.belge_reddet(self.koordinator, ilk, 'İmza eksik')
        self.istek.refresh_from_db()
        self.assertEqual(self.istek.durum[0], 'REDDEDILDI')
        ikinci = services.belge_yukle(self.ogr, BelgeTuru.DIGER, dosya(), istek=self.istek)
        self.istek.refresh_from_db()
        self.assertEqual((self.istek.belge, self.istek.durum[0], ikinci.surum), (ikinci, 'YUKLENDI', 2))
        self.assertTrue(Belge.objects.filter(pk=ilk.pk).exists())

    def test_baska_ogrenci_istege_yanit_veremez(self):
        with self.assertRaises(PermissionDenied):
            services.belge_yukle(self.ogrenci_b.kullanici, BelgeTuru.DIGER, dosya(), istek=self.istek)
        self.assertEqual(self.diskteki_dosyalar(), [])

    def test_istek_kurallari(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'öğrenciden istenemez'):
            services.belge_iste(self.koordinator, self.ogrenci_a, BelgeTuru.RESMI_YAZI, 'x')
        with self.assertRaisesMessage(services.IslemHatasi, 'dönem seçilmesi zorunludur'):
            services.belge_iste(self.koordinator, self.ogrenci_a, BelgeTuru.TRANSKRIPT, 'x')
        with self.assertRaisesMessage(services.IslemHatasi, 'Gerekçe'):
            services.belge_iste(self.koordinator, self.ogrenci_a, BelgeTuru.DIGER, ' ')
        for kullanici in (self.baskan, self.ogr):
            with self.assertRaises(PermissionDenied):
                services.belge_iste(kullanici, self.ogrenci_a, BelgeTuru.DIGER, 'x')

    def test_koordinator_resmi_yazi_yukler_dogrudan_onayli(self):
        belge = services.belge_yukle(self.koordinator, BelgeTuru.RESMI_YAZI, dosya('karar.pdf'),
                                     ogrenci=self.ogrenci_a)
        self.assertEqual((belge.ogrenci, belge.durum, belge.inceleyen),
                         (self.ogrenci_a, BelgeDurumu.ONAYLANDI, self.koordinator))
        with self.assertRaisesMessage(services.IslemHatasi, 'yalnızca koordinatör'):
            services.belge_yukle(self.ogr, BelgeTuru.RESMI_YAZI, dosya())


class MesajEkranTest(GeciciDepo, TestVerisi, TestCase):
    def setUp(self):
        super().setUp()
        self.ogr = self.ogrenci_a.kullanici
        self.mesaj = services.mesaj_gonder(self.ogr, 'Ekte form var', dosya('form.pdf'))

    def test_koordinator_acinca_okunur_rozet_kalkar(self):
        self.client.force_login(self.koordinator)
        self.assertContains(self.client.get(reverse('ana_sayfa')), 'okunmamış mesaj')
        cevap = self.client.get(reverse('yazisma', args=[self.ogrenci_a.pk]))
        self.assertContains(cevap, 'Ekte form var')
        self.assertContains(cevap, reverse('mesaj_eki', args=[self.mesaj.pk]))
        self.mesaj.refresh_from_db()
        self.assertIsNotNone(self.mesaj.okunma_tarihi)
        self.assertNotContains(self.client.get(reverse('ana_sayfa')), 'okunmamış mesaj')

    def test_koordinator_ekli_mesaj_gonderir(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('yazisma', args=[self.ogrenci_a.pk]),
                                 {'metin': 'Karar ekte', 'ek': dosya('karar.pdf')}, follow=True)
        self.assertContains(cevap, 'Mesaj gönderildi.')
        yeni = Mesaj.objects.get(metin='Karar ekte')
        self.assertEqual((yeni.ogrenci, yeni.ek_adi), (self.ogrenci_a, 'karar.pdf'))

    def test_baskan_okur_ama_yazamaz_ve_okundu_yapmaz(self):
        self.client.force_login(self.baskan)
        cevap = self.client.get(reverse('yazisma', args=[self.ogrenci_a.pk]))
        self.assertContains(cevap, 'Ekte form var')
        self.assertNotContains(cevap, 'Yeni mesaj')
        self.assertEqual(self.client.post(reverse('yazisma', args=[self.ogrenci_a.pk]), {'metin': 'x'}).status_code,
                         403)
        self.assertEqual(self.client.get(reverse('mesaj_eki', args=[self.mesaj.pk])).status_code, 200)
        self.mesaj.refresh_from_db()
        self.assertIsNone(self.mesaj.okunma_tarihi)
        self.assertEqual(Mesaj.objects.count(), 1)

    def test_ogrenci_yalnizca_kendi_yazismasini_gorur(self):
        diger = self.ogrenci_b.kullanici
        self.client.force_login(diger)
        self.assertNotContains(self.client.get(reverse('benim_mesajlarim')), 'Ekte form var')
        self.assertEqual(self.client.get(reverse('mesaj_eki', args=[self.mesaj.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('yazisma', args=[self.ogrenci_a.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('mesajlar')).status_code, 403)
        self.client.force_login(self.ogr)
        self.assertContains(self.client.get(reverse('benim_mesajlarim')), 'Ekte form var')
        self.assertEqual(self.client.get(reverse('mesaj_eki', args=[self.mesaj.pk])).status_code, 200)

    def test_girissiz_erisilemez(self):
        for url in (reverse('mesajlar'), reverse('benim_mesajlarim'), reverse('mesaj_eki', args=[self.mesaj.pk])):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_ogrenci_rozeti_ve_okundu(self):
        services.mesaj_gonder(self.koordinator, 'Yanıtım', ogrenci=self.ogrenci_a)
        self.client.force_login(self.ogr)
        self.assertContains(self.client.get(reverse('benim')), 'okunmamış mesaj')
        self.client.get(reverse('benim_mesajlarim'))
        self.assertNotContains(self.client.get(reverse('benim')), 'okunmamış mesaj')

    def test_istek_ekranlari(self):
        self.client.force_login(self.koordinator)
        self.client.post(reverse('belge_iste', args=[self.ogrenci_a.pk]),
                         {'tur': BelgeTuru.DIGER, 'aciklama': 'Muafiyet formu'})
        istek = BelgeIstegi.objects.get()
        # Başka öğrenci bu isteği göremez ve yanıtlayamaz.
        self.client.force_login(self.ogrenci_b.kullanici)
        self.assertNotContains(self.client.get(reverse('belgelerim')), 'Muafiyet formu')
        cevap = self.client.post(reverse('istek_yanitla', args=[istek.pk]), {'dosya': dosya()})
        self.assertEqual(cevap.status_code, 404)
        # Sahibi yükler.
        self.client.force_login(self.ogr)
        self.assertContains(self.client.get(reverse('belgelerim')), 'Muafiyet formu')
        self.client.post(reverse('istek_yanitla', args=[istek.pk]), {'dosya': dosya('muafiyet.pdf')})
        istek.refresh_from_db()
        self.assertEqual(istek.durum[0], 'YUKLENDI')
        self.client.force_login(self.koordinator)
        self.assertContains(self.client.get(reverse('ogrenci_detay', args=[self.ogrenci_a.pk])), 'muafiyet.pdf')

    def test_koordinator_belge_yukleme_ekrani_ve_yetki(self):
        url = reverse('koordinator_belge_yukle', args=[self.ogrenci_a.pk])
        for kullanici in (self.baskan, self.ogr):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.post(url, {'tur': BelgeTuru.RESMI_YAZI, 'dosya': dosya()}).status_code, 403)
            self.assertEqual(self.client.post(reverse('belge_iste', args=[self.ogrenci_a.pk]),
                                              {'tur': BelgeTuru.DIGER, 'aciklama': 'x'}).status_code, 403)
        self.assertFalse(Belge.objects.exists())
        self.client.force_login(self.koordinator)
        self.client.post(url, {'tur': BelgeTuru.RESMI_YAZI, 'dosya': dosya('yk_karari.pdf'), 'aciklama': 'YK kararı'})
        belge = Belge.objects.get()
        self.assertEqual((belge.tur, belge.durum), (BelgeTuru.RESMI_YAZI, BelgeDurumu.ONAYLANDI))
