from django.core.exceptions import PermissionDenied
from django.test import TestCase

from takip import services
from takip.models import (
    DenemeDurumu, DenemeKilitli, Ders, DersDenemesi, IslemKaydi, KuralAyari,
    OnayDurumu, ProgramTuru, SilmeYasak,
)
from takip.services import IslemHatasi

from .yardimci import TestVerisi


class OgrenciEklemeTest(TestVerisi, TestCase):
    def test_hesap_ve_ders_listesi_olusur(self):
        self.assertEqual(self.ogrenci_a.kullanici.username, '1001')
        self.assertTrue(self.ogrenci_a.kullanici.ogrenci_mi)
        self.assertEqual(self.ogrenci_a.ders_listesi.count(), 2)
        self.assertTrue(IslemKaydi.objects.filter(islem='ogrenci_ekle', nesne_id=str(self.ogrenci_a.pk)).exists())

    def test_ayni_ogrenci_no_reddedilir(self):
        with self.assertRaises(IslemHatasi):
            services.ogrenci_ekle(
                self.koordinator, ogrenci_no='1001', ad='X', soyad='Y', okul_eposta='x@example.edu.tr',
                program_turu=ProgramTuru.CAP, ana_dal_bolumu='EEM', protokol=self.protokol,
                kabul_donemi=self.donem,
            )

    def test_protokol_program_turu_uyusmali(self):
        with self.assertRaises(IslemHatasi):
            services.ogrenci_ekle(
                self.koordinator, ogrenci_no='1003', ad='X', soyad='Y', okul_eposta='x@example.edu.tr',
                program_turu=ProgramTuru.YDP, ana_dal_bolumu='EEM', protokol=self.protokol,
                kabul_donemi=self.donem,
            )

    def test_koordinator_disindaki_rol_ekleyemez(self):
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            with self.assertRaises(PermissionDenied):
                services.katalog_dersi_ekle(kullanici, '9999', 'X', 4, 'ZORUNLU')


class SilmeYasagiTest(TestVerisi, TestCase):
    def test_kayitlar_silinemez(self):
        with self.assertRaises(SilmeYasak):
            self.ders1.delete()
        with self.assertRaises(SilmeYasak):
            Ders.objects.all().delete()
        with self.assertRaises(SilmeYasak):
            self.ogrenci_a.delete()

    def test_islem_kaydi_degistirilemez(self):
        kayit = IslemKaydi.objects.first()
        kayit.aciklama = 'değiştirildi'
        with self.assertRaises(SilmeYasak):
            kayit.save()
        with self.assertRaises(SilmeYasak):
            IslemKaydi.objects.update(aciklama='x')
        with self.assertRaises(SilmeYasak):
            kayit.delete()


class DenemeOnayKilidiTest(TestVerisi, TestCase):
    def setUp(self):
        self.kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)

    def test_ogrenci_girisi_onay_bekler_ve_hesaba_girmez(self):
        d = services.deneme_ekle(self.ogrenci_a.kullanici, self.kalem, self.donem, DenemeDurumu.ALINDI)
        self.assertEqual(d.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(self.ogrenci_a.ders_ozeti()['bekleyen_sayi'], 1)

    def test_ogrenci_baskasinin_listesine_giremez(self):
        kalem_b = self.ogrenci_b.ders_listesi.get(ders=self.ders1)
        with self.assertRaises(PermissionDenied):
            services.deneme_ekle(self.ogrenci_a.kullanici, kalem_b, self.donem, DenemeDurumu.PLANLANDI)

    def test_onayli_kayit_kilitlenir_duzeltmeyi_koordinator_yapar(self):
        d = services.deneme_ekle(self.ogrenci_a.kullanici, self.kalem, self.donem, DenemeDurumu.ALINDI)
        services.deneme_onayla(self.koordinator, d)

        d = DersDenemesi.objects.get(pk=d.pk)
        d.durum = DenemeDurumu.GECTI
        d.harf_notu = 'AA'
        with self.assertRaises(DenemeKilitli):
            d.save()

        d = DersDenemesi.objects.get(pk=d.pk)
        services.deneme_duzelt(self.koordinator, d, 'Transkripte göre', durum=DenemeDurumu.GECTI, harf_notu='BB')
        log = IslemKaydi.objects.filter(islem='deneme_duzelt').first()
        self.assertEqual(log.eski_deger['durum'], 'ALINDI')
        self.assertEqual(log.yeni_deger['harf_notu'], 'BB')

    def test_ayni_ders_birden_cok_deneme(self):
        k = self.koordinator
        services.deneme_ekle(k, self.kalem, self.donem, DenemeDurumu.KALDI, 'FF', geriye_donuk=True)
        services.deneme_ekle(k, self.kalem, self.donem2, DenemeDurumu.GECTI, 'CC', geriye_donuk=True)
        self.assertEqual(self.kalem.denemeler.count(), 2)
        self.assertTrue(self.kalem.tamamlandi)
        ozet = self.ogrenci_a.ders_ozeti()
        self.assertEqual((ozet['tamamlanan_akts'], ozet['kalan_akts']), (4, 4))

    def test_gecilmis_ders_listeden_cikarilamaz(self):
        services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.GECTI, 'BA', geriye_donuk=True)
        with self.assertRaises(IslemHatasi):
            services.listeden_ders_cikar(self.koordinator, self.kalem, 'Deneme')

    def test_cikarma_gerekce_ister_ve_silmez(self):
        with self.assertRaises(IslemHatasi):
            services.listeden_ders_cikar(self.koordinator, self.kalem, '  ')
        services.listeden_ders_cikar(self.koordinator, self.kalem, 'Muafiyet protokolü değişti')
        self.kalem.refresh_from_db()
        self.assertFalse(self.kalem.listede)
        self.assertEqual(self.ogrenci_a.ders_listesi.count(), 2)

    def test_iptal_silmez_isaretler(self):
        d = services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.ALINDI)
        services.deneme_iptal(self.koordinator, d, 'Hatalı giriş')
        d.refresh_from_db()
        self.assertEqual(d.onay_durumu, OnayDurumu.IPTAL)


class KuralAyariTest(TestVerisi, TestCase):
    def test_surumlenir_eski_kalir(self):
        k = self.koordinator
        services.kural_ayari_belirle(k, 'cap.mezuniyet_gano', 'CAP', '2.72', 'Mezuniyet GANO', '8c')
        services.kural_ayari_belirle(k, 'cap.mezuniyet_gano', 'CAP', '2.80', 'Mezuniyet GANO', '8c')
        self.assertEqual(KuralAyari.objects.filter(anahtar='cap.mezuniyet_gano').count(), 2)
        self.assertEqual(str(KuralAyari.guncel('cap.mezuniyet_gano').deger), '2.80')
