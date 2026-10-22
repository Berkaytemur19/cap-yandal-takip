"""Koordinatörün öğrenci kartı işlemleri (GANO, ders listesi, kayıt girme/düzeltme/iptal) ve kural ayarları ekranı."""

from django.test import TestCase
from django.urls import reverse

from takip import services
from takip.models import (
    AnaDalGanoKaydi, DenemeDurumu, DersDenemesi, IslemKaydi, KuralAyari, OnayDurumu, ProgramTuru,
)

from .yardimci import TestVerisi


class KoordinatorIslemleriTest(TestVerisi, TestCase):
    def setUp(self):
        self.client.force_login(self.koordinator)
        self.kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)

    def _islem_var(self, islem, aciklama=None):
        kayitlar = IslemKaydi.objects.filter(islem=islem)
        if aciklama is not None:
            kayitlar = kayitlar.filter(aciklama=aciklama)
        return kayitlar.exists()

    # --- GANO ---

    def test_gano_girilir_ve_kaynagi_kaydedilir(self):
        cevap = self.client.post(reverse('gano_gir', args=[self.ogrenci_a.pk]), {
            'yil': 2025, 'donem_turu': 'GUZ', 'gano': '2.85', 'kaynak': 'OBİS transkripti',
        }, follow=True)
        self.assertRedirects(cevap, reverse('ogrenci_detay', args=[self.ogrenci_a.pk]))
        kayit = AnaDalGanoKaydi.objects.get(ogrenci=self.ogrenci_a)
        self.assertEqual(str(kayit.gano), '2.85')
        self.assertEqual(kayit.kaynak, 'OBİS transkripti')
        self.assertContains(cevap, 'OBİS transkripti')
        self.assertTrue(self._islem_var('ana_dal_gano_gir'))

    def test_gecersiz_gano_kaydedilmez(self):
        for gano in ('4.50', '-1'):
            cevap = self.client.post(reverse('gano_gir', args=[self.ogrenci_a.pk]), {
                'yil': 2025, 'donem_turu': 'GUZ', 'gano': gano, 'kaynak': 'x',
            })
            self.assertEqual(cevap.status_code, 400)
        self.assertFalse(AnaDalGanoKaydi.objects.exists())

    def test_kaynaksiz_gano_kaydedilmez(self):
        cevap = self.client.post(reverse('gano_gir', args=[self.ogrenci_a.pk]), {
            'yil': 2025, 'donem_turu': 'GUZ', 'gano': '3.00', 'kaynak': '',
        })
        self.assertEqual(cevap.status_code, 400)
        self.assertFalse(AnaDalGanoKaydi.objects.exists())

    # --- Ders listesi ---

    def test_listeye_ders_eklenir(self):
        yeni = services.katalog_dersi_ekle(self.koordinator, '3301999', 'Bulut Bilişim', 4, 'ZORUNLU')
        self.client.post(reverse('listeye_ders_ekle', args=[self.ogrenci_a.pk]), {
            'ders': yeni.pk, 'yariyil': 5, 'gerekce': 'Protokol güncellendi',
        })
        kalem = self.ogrenci_a.ders_listesi.get(ders=yeni)
        self.assertEqual(kalem.ekleme_gerekcesi, 'Protokol güncellendi')
        self.assertTrue(self._islem_var('liste_ders_ekle', 'Protokol güncellendi'))

    def test_listede_olan_ders_tekrar_eklenmez(self):
        cevap = self.client.post(reverse('listeye_ders_ekle', args=[self.ogrenci_a.pk]), {
            'ders': self.ders1.pk, 'gerekce': 'x',
        })
        self.assertContains(cevap, 'zaten öğrencinin ders listesinde', status_code=400)
        self.assertEqual(self.ogrenci_a.ders_listesi.filter(ders=self.ders1).count(), 1)

    def test_listeden_gerekceyle_cikarilir(self):
        cevap = self.client.post(reverse('listeden_cikar', args=[self.kalem.pk]), {'gerekce': 'Müfredattan kalktı'},
                                 follow=True)
        self.assertRedirects(cevap, reverse('ogrenci_detay', args=[self.ogrenci_a.pk]))
        self.kalem.refresh_from_db()
        self.assertFalse(self.kalem.listede)
        self.assertEqual(self.kalem.cikarma_gerekcesi, 'Müfredattan kalktı')
        self.assertContains(cevap, 'Müfredattan kalktı')

    def test_gerekcesiz_cikarilamaz(self):
        self.client.post(reverse('listeden_cikar', args=[self.kalem.pk]), {'gerekce': '  '})
        self.kalem.refresh_from_db()
        self.assertTrue(self.kalem.listede)

    def test_gecilmis_ders_listeden_cikarilamaz(self):
        services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.GECTI, 'BB')
        cevap = self.client.post(reverse('listeden_cikar', args=[self.kalem.pk]), {'gerekce': 'x'}, follow=True)
        self.assertContains(cevap, 'Geçilmiş veya muaf olunmuş ders listeden çıkarılamaz.')
        self.kalem.refresh_from_db()
        self.assertTrue(self.kalem.listede)

    # --- Kayıt (deneme) girme, düzeltme, iptal ---

    def test_koordinator_geriye_donuk_kayit_girer_dogrudan_onayli(self):
        self.client.post(reverse('kalem_detay', args=[self.kalem.pk]), {
            'yil': 2023, 'donem_turu': 'GUZ', 'durum': 'GECTI', 'harf_notu': 'BA', 'geriye_donuk': 'on',
        })
        deneme = self.kalem.denemeler.get()
        self.assertEqual(deneme.onay_durumu, OnayDurumu.ONAYLANDI)
        self.assertTrue(deneme.geriye_donuk)
        self.assertEqual(str(deneme.donem), '2023-2024 Güz')
        self.assertTrue(self.kalem.tamamlandi)

    def test_notsuz_gecti_kaydedilmez(self):
        cevap = self.client.post(reverse('kalem_detay', args=[self.kalem.pk]), {
            'yil': 2025, 'donem_turu': 'GUZ', 'durum': 'GECTI', 'harf_notu': '',
        })
        self.assertContains(cevap, 'harf notu zorunludur', status_code=400)
        self.assertFalse(self.kalem.denemeler.exists())

    def test_onayli_kayit_gerekceyle_duzeltilir_eski_yeni_deger_kaydedilir(self):
        deneme = services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.KALDI, 'FF')
        on = f'd{deneme.pk}-'
        self.client.post(reverse('deneme_duzelt', args=[deneme.pk]), {
            on + 'yil': 2025, on + 'donem_turu': 'GUZ', on + 'durum': 'GECTI', on + 'harf_notu': 'DD',
            on + 'gerekce': 'Not itirazı sonucu',
        })
        deneme.refresh_from_db()
        self.assertEqual((deneme.durum, deneme.harf_notu), (DenemeDurumu.GECTI, 'DD'))
        kayit = IslemKaydi.objects.get(islem='deneme_duzelt')
        self.assertEqual(kayit.eski_deger['harf_notu'], 'FF')
        self.assertEqual(kayit.yeni_deger['harf_notu'], 'DD')
        self.assertEqual(kayit.aciklama, 'Not itirazı sonucu')

    def test_gerekcesiz_duzeltme_yapilamaz(self):
        deneme = services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.KALDI, 'FF')
        on = f'd{deneme.pk}-'
        cevap = self.client.post(reverse('deneme_duzelt', args=[deneme.pk]), {
            on + 'yil': 2025, on + 'donem_turu': 'GUZ', on + 'durum': 'GECTI', on + 'harf_notu': 'DD',
        }, follow=True)
        self.assertContains(cevap, 'Düzeltme gerekçesi')
        deneme.refresh_from_db()
        self.assertEqual(deneme.harf_notu, 'FF')

    def test_kayit_gerekceyle_iptal_edilir_silinmez(self):
        deneme = services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.ALINDI)
        cevap = self.client.post(reverse('deneme_iptal', args=[deneme.pk]), {'gerekce': 'Yanlış öğrenciye girilmiş'},
                                 follow=True)
        self.assertRedirects(cevap, reverse('kalem_detay', args=[self.kalem.pk]))
        deneme.refresh_from_db()
        self.assertEqual(deneme.onay_durumu, OnayDurumu.IPTAL)
        self.assertContains(cevap, 'Yanlış öğrenciye girilmiş')
        self.assertTrue(DersDenemesi.objects.filter(pk=deneme.pk).exists())

    def test_kalem_sayfasi_acilir(self):
        services.deneme_ekle(self.koordinator, self.kalem, self.donem, DenemeDurumu.ALINDI)
        cevap = self.client.get(reverse('kalem_detay', args=[self.kalem.pk]))
        self.assertContains(cevap, self.ders1.ad)
        self.assertContains(cevap, 'Düzelt / iptal')
        detay = self.client.get(reverse('ogrenci_detay', args=[self.ogrenci_a.pk]))
        self.assertContains(detay, reverse('kalem_detay', args=[self.kalem.pk]))
        self.assertContains(detay, 'GANO gir')


class KuralAyarlariTest(TestVerisi, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        services.kural_ayari_belirle(cls.koordinator, 'cap.mezuniyet_gano', ProgramTuru.CAP, '2.72',
                                     'Mezuniyet için ana dal GANO', '8c')

    def test_yeni_deger_yeni_surum_olarak_eklenir_eskisi_kalir(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('kural_guncelle', args=['cap.mezuniyet_gano']),
                                 {'cap.mezuniyet_gano-deger': '2.80'}, follow=True)
        self.assertContains(cevap, 'sürüm 2')
        surumler = list(KuralAyari.objects.filter(anahtar='cap.mezuniyet_gano').order_by('surum')
                        .values_list('surum', 'deger'))
        self.assertEqual([(s, str(d)) for s, d in surumler], [(1, '2.72'), (2, '2.80')])
        self.assertContains(cevap, 'Eski sürümler (1)')

    def test_ayni_deger_yeni_surum_olusturmaz(self):
        self.client.force_login(self.koordinator)
        self.client.post(reverse('kural_guncelle', args=['cap.mezuniyet_gano']), {'cap.mezuniyet_gano-deger': '2.72'})
        self.assertEqual(KuralAyari.objects.filter(anahtar='cap.mezuniyet_gano').count(), 1)

    def test_olmayan_kural_404(self):
        self.client.force_login(self.koordinator)
        cevap = self.client.post(reverse('kural_guncelle', args=['yok.boyle']), {'yok.boyle-deger': '1'})
        self.assertEqual(cevap.status_code, 404)

    def test_baskan_gorur_ama_degistiremez(self):
        self.client.force_login(self.baskan)
        cevap = self.client.get(reverse('kural_ayarlari'))
        self.assertContains(cevap, 'Salt okunur')
        self.assertNotContains(cevap, reverse('kural_guncelle', args=['cap.mezuniyet_gano']))


class KoordinatorIslemleriYetkiTest(TestVerisi, TestCase):
    """Bölüm başkanı ve öğrenci bu işlemlerin hiçbirini yapamaz: 403, veri ve işlem kaydı değişmez."""

    def test_baskan_ve_ogrenci_403(self):
        kalem = self.ogrenci_a.ders_listesi.get(ders=self.ders1)
        deneme = services.deneme_ekle(self.koordinator, kalem, self.donem, DenemeDurumu.ALINDI)
        services.kural_ayari_belirle(self.koordinator, 'cap.toplam_akts', ProgramTuru.CAP, '240', 'Toplam AKTS', '7-2')
        on = f'd{deneme.pk}-'
        istekler = [
            (reverse('gano_gir', args=[self.ogrenci_a.pk]),
             {'yil': 2025, 'donem_turu': 'GUZ', 'gano': '3', 'kaynak': 'x'}),
            (reverse('listeye_ders_ekle', args=[self.ogrenci_a.pk]), {'ders': self.ders2.pk, 'gerekce': 'x'}),
            (reverse('kalem_detay', args=[kalem.pk]), {'yil': 2025, 'donem_turu': 'BAHAR', 'durum': 'ALINDI'}),
            (reverse('deneme_duzelt', args=[deneme.pk]),
             {on + 'yil': 2025, on + 'donem_turu': 'GUZ', on + 'durum': 'GECTI', on + 'harf_notu': 'AA',
              on + 'gerekce': 'x'}),
            (reverse('deneme_iptal', args=[deneme.pk]), {'gerekce': 'x'}),
            (reverse('listeden_cikar', args=[kalem.pk]), {'gerekce': 'x'}),
            (reverse('kural_guncelle', args=['cap.toplam_akts']), {'cap.toplam_akts-deger': '1'}),
        ]
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('kalem_detay', args=[kalem.pk])).status_code, 403)
            for url, veri in istekler:
                with self.subTest(kullanici=kullanici.username, url=url):
                    self.assertEqual(self.client.post(url, veri).status_code, 403)
        self.client.force_login(self.ogrenci_a.kullanici)
        self.assertEqual(self.client.get(reverse('kural_ayarlari')).status_code, 403)

        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
        deneme.refresh_from_db()
        kalem.refresh_from_db()
        self.assertEqual((deneme.durum, deneme.onay_durumu), (DenemeDurumu.ALINDI, OnayDurumu.ONAYLANDI))
        self.assertTrue(kalem.listede)
        self.assertFalse(AnaDalGanoKaydi.objects.exists())
        self.assertEqual(KuralAyari.objects.count(), 1)
