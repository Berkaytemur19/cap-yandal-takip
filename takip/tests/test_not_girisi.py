"""Dönem sonu not girişi: transkript şartı, onay / ret, kilit ve yetki."""

import datetime

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.models import (
    BelgeTuru, DenemeDurumu, DonemTuru, IslemKaydi, NotGirisi, OnayDurumu,
)

from .test_belgeler import GeciciDepo, dosya
from .yardimci import TestVerisi

# TestVerisi dönemleri 2025-2026 Güz ve Bahar; bu tarihte ikisi de geçmiş dönemdir.
BUGUN = datetime.date(2026, 10, 22)


class NotGirisiTemel(GeciciDepo, TestVerisi):
    def setUp(self):
        super().setUp()
        self.ogr = self.ogrenci_a.kullanici
        self.kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)
        self.deneme = services.deneme_ekle(self.ogr, self.kalem, self.donem, DenemeDurumu.ALINDI)
        services.deneme_onayla(self.koordinator, self.deneme)

    def transkript_yukle(self, ogr=None, donem=None):
        return services.belge_yukle(ogr or self.ogr, BelgeTuru.TRANSKRIPT, dosya('not_belgesi.pdf'),
                                    donem or self.donem)


class NotGirisiServisTest(NotGirisiTemel, TestCase):
    def test_transkript_yuklenmeden_not_gonderilemez(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'yüklenmeden notlar onaya gönderilemez'):
            services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        self.assertFalse(NotGirisi.objects.exists())

    def test_reddedilmis_transkript_sayilmaz(self):
        services.belge_reddet(self.koordinator, self.transkript_yukle(), 'Okunmuyor')
        with self.assertRaisesMessage(services.IslemHatasi, 'yüklenmeden'):
            services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)

    def test_ana_dal_transkripti_yetmez(self):
        services.belge_yukle(self.ogr, BelgeTuru.ANA_DAL_TRANSKRIPTI, dosya('ana_dal.pdf'), self.donem)
        with self.assertRaisesMessage(services.IslemHatasi, 'yüklenmeden'):
            services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)

    def test_onay_bekleyen_transkriptle_gonderilir_ve_hesaba_girmez(self):
        transkript = self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        self.assertEqual((giris.onay_durumu, giris.transkript), (OnayDurumu.BEKLIYOR, transkript))
        self.deneme.refresh_from_db()
        self.assertEqual((self.deneme.durum, self.deneme.harf_notu), (DenemeDurumu.ALINDI, ''))
        self.assertEqual(self.ogrenci_a.ders_ozeti()['tamamlanan_sayi'], 0)
        self.assertTrue(IslemKaydi.objects.filter(islem='not_gir').exists())

    def test_onaylaninca_ders_gecti_olur_ve_kilitli_kalir(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        services.not_onayla(self.koordinator, giris)
        self.deneme.refresh_from_db()
        self.assertEqual((self.deneme.durum, self.deneme.harf_notu), (DenemeDurumu.GECTI, 'BB'))
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.ONAYLANDI)
        self.assertEqual(self.ogrenci_a.ders_ozeti()['tamamlanan_akts'], self.ders1.akts)
        kayit = IslemKaydi.objects.get(islem='deneme_not_isle')
        self.assertEqual((kayit.eski_deger['durum'], kayit.yeni_deger['durum']), ('ALINDI', 'GECTI'))
        # Not işlendikten sonra aynı kayda yeniden not girilemez.
        with self.assertRaisesMessage(services.IslemHatasi, 'bu kayda not girilemez'):
            services.not_gir(self.ogr, [(self.deneme, 'AA', DenemeDurumu.GECTI)], BUGUN)

    def test_reddedilen_giris_kalir_ogrenci_yeniden_gonderir(self):
        self.transkript_yukle()
        [ilk] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        services.not_reddet(self.koordinator, ilk, 'Transkriptte CB yazıyor')
        [ikinci] = services.not_gir(self.ogr, [(self.deneme, 'CB', DenemeDurumu.GECTI)], BUGUN)
        ilk.refresh_from_db()
        self.assertEqual((ilk.onay_durumu, ilk.red_gerekcesi), (OnayDurumu.REDDEDILDI, 'Transkriptte CB yazıyor'))
        self.assertEqual(ikinci.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(NotGirisi.objects.count(), 2)

    def test_gerekcesiz_ret_yapilamaz(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        with self.assertRaisesMessage(services.IslemHatasi, 'Gerekçe'):
            services.not_reddet(self.koordinator, giris, ' ')

    def test_bekleyen_not_varken_ikinci_giris_yapilamaz(self):
        self.transkript_yukle()
        services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        with self.assertRaisesMessage(services.IslemHatasi, 'bu kayda not girilemez'):
            services.not_gir(self.ogr, [(self.deneme, 'BA', DenemeDurumu.GECTI)], BUGUN)

    def test_onaylanmamis_veya_planlanan_kayda_not_girilemez(self):
        kalem2 = self.ogrenci_a.ders_listesi.get(ders=self.ders2)
        bekleyen = services.deneme_ekle(self.ogr, kalem2, self.donem, DenemeDurumu.ALINDI)
        planli = services.deneme_ekle(self.ogr, kalem2, self.donem2, DenemeDurumu.PLANLANDI)
        services.deneme_onayla(self.koordinator, planli)
        self.transkript_yukle()
        for deneme in (bekleyen, planli):
            with self.assertRaisesMessage(services.IslemHatasi, 'bu kayda not girilemez'):
                services.not_gir(self.ogr, [(deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)

    def test_gelecek_doneme_not_girilemez(self):
        # 2025-2026 Güz içindeyken (Kasım 2025) Bahar dönemi henüz gelmemiştir.
        self.assertEqual(services.not_girilebilir_denemeler(self.ogrenci_a, datetime.date(2025, 11, 1)),
                         [self.deneme])
        kalem2 = self.ogrenci_a.ders_listesi.get(ders=self.ders2)
        bahar = services.deneme_ekle(self.ogr, kalem2, self.donem2, DenemeDurumu.ALINDI)
        services.deneme_onayla(self.koordinator, bahar)
        self.assertNotIn(bahar, services.not_girilebilir_denemeler(self.ogrenci_a, datetime.date(2025, 11, 1)))
        self.assertIn(bahar, services.not_girilebilir_denemeler(self.ogrenci_a, BUGUN))

    def test_iptal_edilen_kaydin_bekleyen_notu_onaylanamaz(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        services.deneme_iptal(self.koordinator, self.deneme, 'Yanlış ders')
        with self.assertRaisesMessage(services.IslemHatasi, 'not onaylanamaz'):
            services.not_onayla(self.koordinator, giris)
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.IPTAL)

    def test_baska_ogrencinin_kaydina_not_girilemez(self):
        self.transkript_yukle(ogr=self.ogrenci_b.kullanici)
        with self.assertRaises(PermissionDenied):
            services.not_gir(self.ogrenci_b.kullanici, [(self.deneme, 'AA', DenemeDurumu.GECTI)], BUGUN)

    def test_ogrenci_ve_baskan_onaylayamaz(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)], BUGUN)
        for kullanici in (self.ogr, self.baskan):
            with self.assertRaises(PermissionDenied):
                services.not_onayla(kullanici, giris)
            with self.assertRaises(PermissionDenied):
                services.not_reddet(kullanici, giris, 'x')

    def test_ogrenci_hala_dogrudan_gecti_kaydi_giremez(self):
        kalem2 = self.ogrenci_a.ders_listesi.get(ders=self.ders2)
        with self.assertRaisesMessage(services.IslemHatasi, 'Not girişi'):
            services.deneme_ekle(self.ogr, kalem2, self.donem, DenemeDurumu.GECTI, 'AA')


class NotGirisiEkranTest(NotGirisiTemel, TestCase):
    def test_transkript_yoksa_form_kapali_ve_yukleme_baglantisi_var(self):
        self.client.force_login(self.ogr)
        cevap = self.client.get(reverse('not_girisi'))
        self.assertContains(cevap, self.ders1.kod)
        self.assertContains(cevap, f'?tur={BelgeTuru.TRANSKRIPT}&amp;donem={self.donem.pk}')
        self.assertContains(cevap, 'disabled')

    def test_ogrenci_notu_gonderir_koordinator_onaylar(self):
        self.transkript_yukle()
        self.client.force_login(self.ogr)
        cevap = self.client.post(reverse('not_girisi'), {
            'donem': self.donem.pk, f'harf_{self.deneme.pk}': 'BA', f'durum_{self.deneme.pk}': 'GECTI',
        }, follow=True)
        self.assertContains(cevap, '1 dersin notu onaya gönderildi.')
        giris = NotGirisi.objects.get()

        self.client.force_login(self.koordinator)
        liste = self.client.get(reverse('onay_bekleyenler'))
        self.assertContains(liste, reverse('belge_dosyasi', args=[giris.transkript.pk]))
        self.assertContains(liste, 'BA · Geçti')
        self.client.post(reverse('not_onayla', args=[giris.pk]))
        self.deneme.refresh_from_db()
        self.assertEqual((self.deneme.durum, self.deneme.harf_notu), (DenemeDurumu.GECTI, 'BA'))

    def test_yarim_satir_gonderilmez(self):
        self.transkript_yukle()
        self.client.force_login(self.ogr)
        cevap = self.client.post(reverse('not_girisi'), {
            'donem': self.donem.pk, f'harf_{self.deneme.pk}': 'BA',
        }, follow=True)
        self.assertContains(cevap, 'birlikte seçilmelidir')
        self.assertFalse(NotGirisi.objects.exists())

    def test_koordinator_gerekceyle_reddeder_ogrenci_gerekceyi_gorur(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)])
        self.client.force_login(self.koordinator)
        self.client.post(reverse('not_reddet', args=[giris.pk]), {'gerekce': 'Transkriptle uyuşmuyor'})
        self.client.force_login(self.ogr)
        self.assertContains(self.client.get(reverse('not_girisi')), 'Transkriptle uyuşmuyor')

    def test_yetkisiz_erisim(self):
        self.transkript_yukle()
        [giris] = services.not_gir(self.ogr, [(self.deneme, 'BB', DenemeDurumu.GECTI)])
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogr, self.ogrenci_b.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.post(reverse('not_onayla', args=[giris.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse('not_reddet', args=[giris.pk]), {'gerekce': 'x'}).status_code,
                             403)
        for kullanici in (self.baskan, self.koordinator):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('not_girisi')).status_code, 403)
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
        giris.refresh_from_db()
        self.assertEqual(giris.onay_durumu, OnayDurumu.BEKLIYOR)

    def test_baska_ogrenci_kendi_sayfasinda_bu_dersi_gormez_ve_gonderemez(self):
        diger = self.ogrenci_b.kullanici
        self.transkript_yukle(ogr=diger)
        self.client.force_login(diger)
        self.assertNotContains(self.client.get(reverse('not_girisi')), f'harf_{self.deneme.pk}')
        self.client.post(reverse('not_girisi'), {
            'donem': self.donem.pk, f'harf_{self.deneme.pk}': 'AA', f'durum_{self.deneme.pk}': 'GECTI',
        })
        self.assertFalse(NotGirisi.objects.exists())
