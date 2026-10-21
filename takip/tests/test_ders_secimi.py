"""Öğrencinin ders seçimi ve ders talepleri: servis kuralları, ekranlar ve yetki."""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.models import (
    DenemeDurumu, DersDenemesi, DersTalebi, DonemTuru, IslemKaydi, OnayDurumu, TalepDurumu,
)

from .yardimci import TestVerisi

EKIM_2026 = date(2026, 10, 21)


class DonemHesabiTest(TestCase):
    def test_donem_tarihten(self):
        self.assertEqual(services.donem_tarihten(date(2026, 10, 21)), (2026, DonemTuru.GUZ))
        self.assertEqual(services.donem_tarihten(date(2027, 1, 15)), (2026, DonemTuru.GUZ))
        self.assertEqual(services.donem_tarihten(date(2027, 3, 1)), (2026, DonemTuru.BAHAR))
        self.assertEqual(services.donem_tarihten(date(2027, 7, 10)), (2026, DonemTuru.YAZ))

    def test_secilebilir_donemler(self):
        self.assertEqual(services.secilebilir_donemler(EKIM_2026), [
            (2026, DonemTuru.GUZ, DenemeDurumu.ALINDI), (2026, DonemTuru.BAHAR, DenemeDurumu.PLANLANDI),
        ])
        self.assertEqual(services.secilebilir_donemler(date(2027, 3, 1))[1],
                         (2027, DonemTuru.GUZ, DenemeDurumu.PLANLANDI))


class DersSecServisTest(TestVerisi, TestCase):
    def setUp(self):
        self.ogr = self.ogrenci_a.kullanici
        self.kalem1 = self.ogrenci_a.ders_listesi.get(ders=self.ders1)
        self.kalem2 = self.ogrenci_a.ders_listesi.get(ders=self.ders2)

    def test_bu_donem_alindi_sonraki_donem_planlandi(self):
        bu = services.ders_sec(self.ogr, [self.kalem1], 2026, DonemTuru.GUZ, tarih=EKIM_2026)
        sonraki = services.ders_sec(self.ogr, [self.kalem2], 2026, DonemTuru.BAHAR, tarih=EKIM_2026)
        self.assertEqual(bu[0].durum, DenemeDurumu.ALINDI)
        self.assertEqual(sonraki[0].durum, DenemeDurumu.PLANLANDI)
        for deneme in bu + sonraki:
            self.assertEqual(deneme.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(IslemKaydi.objects.filter(islem='deneme_ekle', kullanici=self.ogr).count(), 2)

    def test_secilemeyen_donem(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'Bu dönem için ders seçimi yapılamaz.'):
            services.ders_sec(self.ogr, [self.kalem1], 2025, DonemTuru.GUZ, tarih=EKIM_2026)

    def test_ayni_donemde_iki_kez_secilemez(self):
        services.ders_sec(self.ogr, [self.kalem1], 2026, DonemTuru.GUZ, tarih=EKIM_2026)
        with self.assertRaisesMessage(services.IslemHatasi, self.ders1.kod):
            services.ders_sec(self.ogr, [self.kalem1], 2026, DonemTuru.GUZ, tarih=EKIM_2026)

    def test_baskasinin_dersi_secilemez_ve_hicbir_sey_kaydedilmez(self):
        baskasinin = self.ogrenci_b.ders_listesi.get(ders=self.ders2)
        with self.assertRaises(PermissionDenied):
            services.ders_sec(self.ogr, [self.kalem1, baskasinin], 2026, DonemTuru.GUZ, tarih=EKIM_2026)
        self.assertFalse(DersDenemesi.objects.filter(liste_kalemi__ogrenci=self.ogrenci_a).exists())

    def test_koordinator_ders_sec_kullanamaz(self):
        with self.assertRaises(PermissionDenied):
            services.ders_sec(self.koordinator, [self.kalem1], 2026, DonemTuru.GUZ, tarih=EKIM_2026)

    def test_pasif_ders_secilemez(self):
        services.katalog_dersi_aktiflik(self.koordinator, self.ders1, False)
        self.kalem1.refresh_from_db()
        with self.assertRaisesMessage(services.IslemHatasi, 'pasif'):
            services.ders_sec(self.ogr, [self.kalem1], 2026, DonemTuru.GUZ, tarih=EKIM_2026)


class TalepServisTest(TestVerisi, TestCase):
    def setUp(self):
        self.ogr = self.ogrenci_a.kullanici
        self.ders3 = services.katalog_dersi_ekle(self.koordinator, '3301753', 'Veri Bilimi', 4, 'ZORUNLU')

    def test_katalogdaki_ders_icin_talep(self):
        talep = services.talep_gonder(self.ogr, 'İlgi alanım', ders=self.ders3)
        self.assertEqual(talep.durum, TalepDurumu.BEKLIYOR)
        self.assertTrue(IslemKaydi.objects.filter(islem='talep_gonder', nesne_id=str(talep.pk)).exists())

    def test_ders_ya_da_ad_ikisinden_biri(self):
        with self.assertRaises(services.IslemHatasi):
            services.talep_gonder(self.ogr, 'x')
        with self.assertRaises(services.IslemHatasi):
            services.talep_gonder(self.ogr, 'x', ders=self.ders3, istenen_ders='Başka ders')

    def test_aciklama_zorunlu(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'açıklamanız zorunludur'):
            services.talep_gonder(self.ogr, '  ', istenen_ders='3301999 Bulut Bilişim')

    def test_listedeki_ders_ve_tekrar_talep_engellenir(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'zaten ders listenizde'):
            services.talep_gonder(self.ogr, 'x', ders=self.ders1)
        services.talep_gonder(self.ogr, 'x', ders=self.ders3)
        with self.assertRaisesMessage(services.IslemHatasi, 'bekleyen bir talebiniz'):
            services.talep_gonder(self.ogr, 'x', ders=self.ders3)

    def test_kabul_dersi_listeye_ekler(self):
        talep = services.talep_gonder(self.ogr, 'Bulut dersi', istenen_ders='Bulut Bilişim')
        services.talep_kabul(self.koordinator, talep, self.ders3, 'Kataloğa eklendi')
        talep.refresh_from_db()
        self.assertEqual(talep.durum, TalepDurumu.KABUL)
        self.assertEqual(talep.eklenen_kalem.ders, self.ders3)
        self.assertTrue(self.ogrenci_a.ders_listesi.filter(ders=self.ders3, listede=True).exists())
        with self.assertRaisesMessage(services.IslemHatasi, 'zaten yanıtlanmış'):
            services.talep_kabul(self.koordinator, talep, self.ders3)

    def test_ret_gerekce_ister(self):
        talep = services.talep_gonder(self.ogr, 'x', ders=self.ders3)
        with self.assertRaises(services.IslemHatasi):
            services.talep_reddet(self.koordinator, talep, '')
        services.talep_reddet(self.koordinator, talep, 'Protokolde yok')
        talep.refresh_from_db()
        self.assertEqual((talep.durum, talep.yanit), (TalepDurumu.RED, 'Protokolde yok'))

    def test_ogrenci_talep_yanitlayamaz(self):
        talep = services.talep_gonder(self.ogr, 'x', ders=self.ders3)
        with self.assertRaises(PermissionDenied):
            services.talep_kabul(self.ogr, talep, self.ders3)


class DersSecEkranTest(TestVerisi, TestCase):
    def setUp(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        yil, tur, _ = services.secilebilir_donemler()[0]
        self.bu_donem = f'{yil}-{tur}'
        self.kalem1 = self.ogrenci_a.ders_listesi.get(ders=self.ders1)

    def test_sayfa_kendi_derslerini_gosterir(self):
        cevap = self.client.get(reverse('ders_sec'))
        self.assertContains(cevap, self.ders1.ad)
        self.assertContains(cevap, f'value="{self.kalem1.pk}"')

    def test_tamamlanan_ders_secenekte_yok(self):
        services.deneme_ekle(self.koordinator, self.kalem1, self.donem, DenemeDurumu.GECTI, 'BB',
                             geriye_donuk=True)
        cevap = self.client.get(reverse('ders_sec'))
        self.assertNotContains(cevap, f'value="{self.kalem1.pk}"')

    def test_ders_secimi_onaya_gider(self):
        cevap = self.client.post(reverse('ders_sec'), {
            'islem': 'sec', 'donem': self.bu_donem, 'kalemler': [self.kalem1.pk],
        }, follow=True)
        self.assertContains(cevap, '1 ders seçildi')
        deneme = DersDenemesi.objects.get(liste_kalemi=self.kalem1)
        self.assertEqual((deneme.durum, deneme.onay_durumu), (DenemeDurumu.ALINDI, OnayDurumu.BEKLIYOR))

    def test_url_ile_baskasinin_dersi_gonderilemez(self):
        baskasinin = self.ogrenci_b.ders_listesi.get(ders=self.ders1)
        cevap = self.client.post(reverse('ders_sec'), {
            'islem': 'sec', 'donem': self.bu_donem, 'kalemler': [baskasinin.pk],
        })
        self.assertEqual(cevap.status_code, 200)  # form hatasıyla geri döner
        self.assertFalse(DersDenemesi.objects.exists())

    def test_talep_gonderilir(self):
        cevap = self.client.post(reverse('ders_sec'), {
            'islem': 'talep', 'istenen_ders': '3301999 Bulut Bilişim', 'aciklama': 'Ana dalımda yok',
        }, follow=True)
        self.assertContains(cevap, 'talebiniz koordinatöre gönderildi')
        self.assertContains(cevap, '3301999 Bulut Bilişim')
        self.assertEqual(DersTalebi.objects.get().ogrenci, self.ogrenci_a)

    def test_baska_rol_ders_sec_sayfasini_acamaz(self):
        for kullanici in (self.koordinator, self.baskan):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('ders_sec')).status_code, 403)


class TalepEkranTest(TestVerisi, TestCase):
    def setUp(self):
        self.ders3 = services.katalog_dersi_ekle(self.koordinator, '3301753', 'Veri Bilimi', 4, 'ZORUNLU')
        self.talep = services.talep_gonder(self.ogrenci_a.kullanici, 'İlgi alanım', ders=self.ders3)

    def test_koordinator_listede_gorur_ve_kabul_eder(self):
        self.client.force_login(self.koordinator)
        self.assertContains(self.client.get(reverse('talepler')), 'İlgi alanım')
        cevap = self.client.post(reverse('talep_kabul', args=[self.talep.pk]), {'ders': self.ders3.pk},
                                 follow=True)
        self.assertContains(cevap, 'Talep kabul edildi')
        self.assertTrue(self.ogrenci_a.ders_listesi.filter(ders=self.ders3).exists())

    def test_ogrenci_ve_baskan_talep_yanitlayamaz(self):
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('talepler')).status_code, 403)
            cevap = self.client.post(reverse('talep_kabul', args=[self.talep.pk]), {'ders': self.ders3.pk})
            self.assertEqual(cevap.status_code, 403)
            cevap = self.client.post(reverse('talep_reddet', args=[self.talep.pk]), {'gerekce': 'x'})
            self.assertEqual(cevap.status_code, 403)
        self.talep.refresh_from_db()
        self.assertEqual(self.talep.durum, TalepDurumu.BEKLIYOR)
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
