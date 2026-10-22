"""Yönerge kural kontrolleri, kalıcı uyarılar ve koordinatör kararı."""

import datetime

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.management.commands.seed_demo import KURAL_AYARLARI
from takip.models import (
    DenemeDurumu, IslemKaydi, KayitDurumu, KuralUyarisi, ProgramTuru, SilmeYasak, UyariDegistirilemez,
    UyariSeviyesi,
)

from .yardimci import TestVerisi

BUGUN = datetime.date(2026, 10, 22)  # 2026-2027 Güz; 2025-2026 Güz ve Bahar tamamlanmış dönemler


class KuralTestVerisi(TestVerisi):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        k = cls.koordinator
        for anahtar, program, deger, aciklama, madde in KURAL_AYARLARI:
            services.kural_ayari_belirle(k, anahtar, program, deger, aciklama, madde)
        cls.donem0 = services.donem_bul_veya_ekle(k, 2024, 'BAHAR')

    def kontrol(self, ogrenci, tarih=BUGUN):
        return {u.kod: u for u in services.kurallari_kontrol_et(ogrenci, tarih)}

    def gano(self, ogrenci, donem, deger):
        services.ana_dal_gano_gir(self.koordinator, ogrenci, donem, deger, 'Test transkripti')

    def ders(self, ogrenci, ders, donem, durum, harf=''):
        kalem = ogrenci.ders_listesi.get(ders=ders, listede=True)
        return services.deneme_ekle(self.koordinator, kalem, donem, durum, harf)


class CapGanoTest(KuralTestVerisi, TestCase):
    def test_ilk_dusus_uyari_ikinci_dusus_kritik(self):
        self.gano(self.ogrenci_a, self.donem, '2.60')
        u = self.kontrol(self.ogrenci_a)['cap.gano']
        self.assertEqual(u.seviye, UyariSeviyesi.UYARI)
        self.assertIn('bir defalık hak kullanıldı', u.mesaj)
        self.gano(self.ogrenci_a, self.donem2, '2.65')
        u = self.kontrol(self.ogrenci_a)['cap.gano']
        self.assertEqual(u.seviye, UyariSeviyesi.KRITIK)
        self.assertIn('ikinci kez', u.mesaj)

    def test_alt_sinirin_altina_ilk_seferde_kritik(self):
        self.gano(self.ogrenci_a, self.donem, '2.40')
        self.assertEqual(self.kontrol(self.ogrenci_a)['cap.gano'].seviye, UyariSeviyesi.KRITIK)

    def test_toparlaninca_uyari_kapanir_gecmiste_kalir(self):
        self.gano(self.ogrenci_a, self.donem, '2.60')
        ilk = self.kontrol(self.ogrenci_a)['cap.gano']
        self.gano(self.ogrenci_a, self.donem2, '2.90')
        yeni = self.kontrol(self.ogrenci_a)['cap.gano']
        ilk.refresh_from_db()
        self.assertFalse(ilk.acik)
        self.assertEqual(ilk.mesaj.split(':')[0], 'Ana dal GANO 2.60 < 2.72 (2025-2026 Güz)')
        self.assertEqual(yeni.seviye, UyariSeviyesi.BILGI)  # hak kullanıldı bilgisi kalır

    def test_ayni_sonuc_tekrar_kontrolde_yeni_uyari_acmaz(self):
        self.gano(self.ogrenci_a, self.donem, '2.60')
        self.kontrol(self.ogrenci_a)
        sayi = KuralUyarisi.objects.count()
        self.kontrol(self.ogrenci_a)
        self.assertEqual(KuralUyarisi.objects.count(), sayi)

    def test_kural_degisince_eski_kontrol_yeniden_yazilmaz(self):
        self.gano(self.ogrenci_a, self.donem, '2.60')
        eski = self.kontrol(self.ogrenci_a)['cap.gano']
        services.kural_ayari_belirle(self.koordinator, 'cap.gano_kayit_silme', ProgramTuru.CAP, '2.50', 'x', '9e')
        eski.refresh_from_db()
        self.assertFalse(eski.acik)
        self.assertEqual(eski.kurallar['cap.gano_kayit_silme'], {'deger': '2.72', 'surum': 1, 'madde': '9e'})
        self.assertIn('< 2.72', eski.mesaj)
        # Yeni eşikle (2.50) 2.60 artık eşik altında değil: açık GANO uyarısı kalmaz.
        self.assertNotIn('cap.gano', self.kontrol(self.ogrenci_a))

    def test_uyari_degistirilemez_ve_silinemez(self):
        self.gano(self.ogrenci_a, self.donem, '2.60')
        u = self.kontrol(self.ogrenci_a)['cap.gano']
        u.mesaj = 'değiştirilmiş'
        with self.assertRaises(UyariDegistirilemez):
            u.save()
        with self.assertRaises(SilmeYasak):
            KuralUyarisi.objects.all().delete()


class DersAlmamaVeSureTest(KuralTestVerisi, TestCase):
    def test_iki_donem_ders_almayan_kritik(self):
        u = self.kontrol(self.ogrenci_a)['cap.ders_almama']
        self.assertEqual(u.seviye, UyariSeviyesi.KRITIK)
        self.assertEqual(u.olcum['ders_alinmayan_donemler'], ['2025-2026 Güz', '2025-2026 Bahar'])

    def test_bir_donem_ders_almayan_uyari(self):
        self.ders(self.ogrenci_a, self.ders1, self.donem, DenemeDurumu.GECTI, 'BB')
        self.assertEqual(self.kontrol(self.ogrenci_a)['cap.ders_almama'].seviye, UyariSeviyesi.UYARI)
        self.ders(self.ogrenci_a, self.ders2, self.donem2, DenemeDurumu.ALINDI)
        self.assertNotIn('cap.ders_almama', self.kontrol(self.ogrenci_a))

    def test_yalnizca_onayli_kayit_sayilir(self):
        kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)
        services.deneme_ekle(self.ogrenci_a.kullanici, kalem, self.donem2, DenemeDurumu.ALINDI)  # onay bekliyor
        self.assertEqual(self.kontrol(self.ogrenci_a)['cap.ders_almama'].seviye, UyariSeviyesi.KRITIK)

    def test_azami_sure(self):
        self.assertNotIn('cap.azami_sure', self.kontrol(self.ogrenci_a))
        self.assertEqual(self.kontrol(self.ogrenci_a, datetime.date(2031, 10, 1))['cap.azami_sure'].seviye,
                         UyariSeviyesi.UYARI)
        self.assertEqual(self.kontrol(self.ogrenci_a, datetime.date(2032, 10, 1))['cap.azami_sure'].seviye,
                         UyariSeviyesi.KRITIK)

    def test_mezuniyet_sartlari_bilgisi(self):
        self.ders(self.ogrenci_a, self.ders1, self.donem, DenemeDurumu.GECTI, 'BB')
        self.ders(self.ogrenci_a, self.ders2, self.donem2, DenemeDurumu.GECTI, 'CC')
        self.gano(self.ogrenci_a, self.donem2, '2.80')
        u = self.kontrol(self.ogrenci_a)['cap.mezuniyet']
        self.assertEqual(u.seviye, UyariSeviyesi.BILGI)
        self.assertIn('mezuniyet şartları sağlanıyor', u.mesaj)
        self.assertNotIn('cap.ders_almama', self.kontrol(self.ogrenci_a))


class YandalTest(KuralTestVerisi, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        k = cls.koordinator
        dersler = [cls.ders1, cls.ders2] + [
            services.katalog_dersi_ekle(k, f'Y{i}', f'Yandal dersi {i}', 5, 'ZORUNLU') for i in range(5)]
        cls.ydp_protokol = services.protokol_ekle(k, 'Test YDP', ProgramTuru.YDP, 'Makine', [(d, 3) for d in dersler])
        cls.ydp, _ = services.ogrenci_ekle(
            k, ogrenci_no='2001', ad='Yan', soyad='Dal', okul_eposta='2001@ogr.example.edu.tr',
            program_turu=ProgramTuru.YDP, ana_dal_bolumu='Makine', protokol=cls.ydp_protokol,
            kabul_donemi=cls.donem0, sifre='Test.12345',
        )

    def test_yandal_ortalamasi_iki_donem_altinda_kritik(self):
        # 2025-2026 Bahar sonunda ortalama (1.0 + 0) / 2 = 0.50: bir dönem sonu altında → uyarı.
        self.ders(self.ydp, self.ders1, self.donem2, DenemeDurumu.GECTI, 'DD')
        self.ders(self.ydp, self.ders2, self.donem2, DenemeDurumu.KALDI, 'FF')
        u = self.kontrol(self.ydp)['ydp.yandal_gano']
        self.assertEqual(u.seviye, UyariSeviyesi.UYARI)
        self.assertEqual(u.kurallar['not.katsayi.DD']['deger'], '1.00')
        self.assertEqual(str(services.kurallar.ogrenci_program_ortalamasi(self.ydp)), '0.50')
        # 2026-2027 Güz sonunda da altında kalırsa (ders alınmasa da ortalama değişmez) → üst üste iki dönem.
        u = self.kontrol(self.ydp, datetime.date(2027, 3, 1))['ydp.yandal_gano']
        self.assertEqual(u.seviye, UyariSeviyesi.KRITIK)

    def test_dersi_gecince_ortalama_esigi_asar(self):
        self.ders(self.ydp, self.ders1, self.donem, DenemeDurumu.KALDI, 'FF')
        self.ders(self.ydp, self.ders2, self.donem2, DenemeDurumu.GECTI, 'AA')
        # Güz sonu 0.00 (altında), Bahar sonu 2.00 (eşikte, altında değil) → uyarı yok.
        self.assertNotIn('ydp.yandal_gano', self.kontrol(self.ydp))

    def test_tekrar_edilen_derste_son_not_gecerli(self):
        self.ders(self.ydp, self.ders1, self.donem, DenemeDurumu.KALDI, 'FF')
        self.ders(self.ydp, self.ders1, self.donem2, DenemeDurumu.GECTI, 'AA')
        self.assertEqual(str(services.kurallar.ogrenci_program_ortalamasi(self.ydp)), '4.00')
        self.assertNotIn('ydp.yandal_gano', self.kontrol(self.ydp))

    def test_ana_dal_gano_2_30_alti_kritik(self):
        self.gano(self.ydp, self.donem2, '2.20')
        self.assertEqual(self.kontrol(self.ydp)['ydp.ana_dal_gano'].seviye, UyariSeviyesi.KRITIK)

    def test_ders_plani_alt_siniri(self):
        self.assertNotIn('ydp.ders_plani', self.kontrol(self.ydp))  # 7 ders, 33 AKTS
        for kalem in self.ydp.ders_listesi.filter(ders__kod__in=['Y0', 'Y1']):
            services.listeden_ders_cikar(self.koordinator, kalem, 'Plan değişti')
        u = self.kontrol(self.ydp)['ydp.ders_plani']
        self.assertEqual((u.seviye, u.olcum), (UyariSeviyesi.UYARI, {'akts': 23, 'ders_sayisi': 5}))


class KararTest(KuralTestVerisi, TestCase):
    def test_koordinator_gerekceyle_karar_verir_uyarilar_kapanir(self):
        self.gano(self.ogrenci_a, self.donem, '2.40')
        self.assertIn('cap.gano', self.kontrol(self.ogrenci_a))
        self.client.force_login(self.koordinator)
        self.client.post(reverse('karar_ver', args=[self.ogrenci_a.pk]),
                         {'yeni_durum': KayitDurumu.KAYDI_SILINDI, 'gerekce': 'YK kararı 2026/15 (sentetik)'})
        self.ogrenci_a.refresh_from_db()
        self.assertEqual(self.ogrenci_a.kayit_durumu, KayitDurumu.KAYDI_SILINDI)
        self.assertEqual(self.ogrenci_a.durum_gerekcesi, 'YK kararı 2026/15 (sentetik)')
        self.assertTrue(IslemKaydi.objects.filter(islem='kayit_durumu_karari').exists())
        self.assertFalse(self.ogrenci_a.uyarilar.filter(kapanma_tarihi__isnull=True).exists())
        self.assertIn('Kayıt durumu', self.ogrenci_a.uyarilar.first().kapanma_nedeni)
        with self.assertRaisesMessage(services.IslemHatasi, 'aktif olmayan'):
            services.ders_sec(self.ogrenci_a.kullanici, [self.ogrenci_a.ders_listesi.first()], 2026, 'GUZ')

    def test_karar_kurallari(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'programı için verilemez'):
            services.kayit_durumu_degistir(self.koordinator, self.ogrenci_a, KayitDurumu.SERTIFIKA_ALDI, 'x')
        with self.assertRaisesMessage(services.IslemHatasi, 'Gerekçe'):
            services.kayit_durumu_degistir(self.koordinator, self.ogrenci_a, KayitDurumu.MEZUN, '')
        with self.assertRaisesMessage(services.IslemHatasi, 'zaten'):
            services.kayit_durumu_degistir(self.koordinator, self.ogrenci_a, KayitDurumu.AKTIF, 'x')
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            with self.assertRaises(PermissionDenied):
                services.kayit_durumu_degistir(kullanici, self.ogrenci_a, KayitDurumu.MEZUN, 'x')

    def test_ekran_yetkileri(self):
        self.gano(self.ogrenci_a, self.donem, '2.40')
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.post(reverse('karar_ver', args=[self.ogrenci_a.pk]),
                                              {'yeni_durum': 'MEZUN', 'gerekce': 'x'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('kurallari_kontrol_et')).status_code, 403)
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
        self.ogrenci_a.refresh_from_db()
        self.assertEqual(self.ogrenci_a.kayit_durumu, KayitDurumu.AKTIF)
        # Başkan uyarıları görür; öğrenci uyarılar sayfasını göremez ama kendi uyarısını kendi sayfasında görür.
        self.client.force_login(self.baskan)
        self.assertContains(self.client.get(reverse('uyarilar')), 'ÇAP Md 9e')
        self.client.force_login(self.ogrenci_a.kullanici)
        self.assertEqual(self.client.get(reverse('uyarilar')).status_code, 403)
        self.assertContains(self.client.get(reverse('benim')), 'ÇAP Md 9e')
        self.client.force_login(self.ogrenci_b.kullanici)
        self.assertNotContains(self.client.get(reverse('benim')), '2.40')

    def test_kontrol_dugmesi_ve_komut(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('kurallari_kontrol_et'), follow=True)
        self.assertContains(cevap, 'öğrenci güncel kural ayarlarıyla kontrol edildi')
        from django.core.management import call_command
        from io import StringIO
        cikti = StringIO()
        call_command('kural_kontrol', stdout=cikti)
        self.assertIn('öğrenci kontrol edildi', cikti.getvalue())


class ErtelemeTest(KuralTestVerisi, TestCase):
    def test_toplu_giriste_ara_durum_uyarisi_acilmaz(self):
        with services.kontroller_ertelenmis():
            yeni, _ = services.ogrenci_ekle(
                self.koordinator, ogrenci_no='3001', ad='Toplu', soyad='Giris', okul_eposta='3001@ogr.example.edu.tr',
                program_turu=ProgramTuru.CAP, ana_dal_bolumu='EEM', protokol=self.protokol,
                kabul_donemi=self.donem, sifre='Test.12345')
            self.ders(yeni, self.ders1, self.donem, DenemeDurumu.GECTI, 'BB')
            self.ders(yeni, self.ders2, self.donem2, DenemeDurumu.GECTI, 'BB')
            self.assertFalse(yeni.uyarilar.exists())
        self.assertFalse(yeni.uyarilar.filter(kod='cap.ders_almama').exists())
