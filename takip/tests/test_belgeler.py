"""Belge yükleme: dosya kontrolü, sürümler, onay / ret, yetki kontrollü indirme."""

import hashlib
import shutil
import tempfile
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from takip import services
from takip.models import Belge, BelgeDurumu, BelgeTuru, IslemKaydi, SilmeYasak

from .yardimci import TestVerisi

PDF = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n'
PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
EXE = b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00' + b'\x00' * 64


def dosya(ad='form.pdf', icerik=PDF):
    return SimpleUploadedFile(ad, icerik)


class GeciciDepo:
    """Her test belgeleri geçici bir klasöre yazar; gerçek korumali_dosyalar klasörüne dokunulmaz."""

    def setUp(self):
        super().setUp()
        self.depo_koku = Path(tempfile.mkdtemp())
        ayar = override_settings(KORUMALI_DOSYA_KOKU=self.depo_koku)
        ayar.enable()
        self.addCleanup(ayar.disable)
        self.addCleanup(shutil.rmtree, self.depo_koku, ignore_errors=True)

    def diskteki_dosyalar(self):
        return [p for p in self.depo_koku.rglob('*') if p.is_file()]


class BelgeServisTest(GeciciDepo, TestVerisi, TestCase):
    def setUp(self):
        super().setUp()
        self.ogr = self.ogrenci_a.kullanici

    def test_pdf_yuklenir_ve_rastgele_adla_saklanir(self):
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('imzali form.pdf'))
        self.assertEqual((belge.durum, belge.surum, belge.mime_turu),
                         (BelgeDurumu.BEKLIYOR, 1, 'application/pdf'))
        self.assertEqual(belge.orijinal_ad, 'imzali form.pdf')
        self.assertEqual(belge.sha256, hashlib.sha256(PDF).hexdigest())
        disk = self.depo_koku / belge.dosya_yolu
        self.assertEqual(disk.read_bytes(), PDF)
        self.assertNotIn('imzali', belge.dosya_yolu)  # öğrencinin verdiği ad diskte kullanılmaz
        self.assertTrue(belge.dosya_yolu.startswith('belgeler/1001/'))
        self.assertTrue(IslemKaydi.objects.filter(islem='belge_yukle', nesne_id=str(belge.pk)).exists())

    def test_uzantisi_pdf_olan_exe_reddedilir_ve_diske_yazilmaz(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'Yalnızca PDF, JPG veya PNG'):
            services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('form.pdf', EXE))
        self.assertFalse(Belge.objects.exists())
        self.assertEqual(self.diskteki_dosyalar(), [])

    def test_uzanti_icerikle_uyusmali(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'uyuşmuyor'):
            services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('form.pdf', PNG))
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('foto.png', PNG))
        self.assertTrue(belge.dosya_yolu.endswith('.png'))

    @override_settings(BELGE_AZAMI_BOYUT=50)
    def test_boyut_siniri(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'en fazla'):
            services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('form.pdf', PDF + b'0' * 100))

    def test_bos_dosya(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'boş'):
            services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya('form.pdf', b''))

    def test_transkript_donem_ister(self):
        with self.assertRaisesMessage(services.IslemHatasi, 'dönem seçilmesi zorunludur'):
            services.belge_yukle(self.ogr, BelgeTuru.TRANSKRIPT, dosya())
        belge = services.belge_yukle(self.ogr, BelgeTuru.TRANSKRIPT, dosya(), donem=self.donem)
        self.assertEqual(belge.donem, self.donem)

    def test_yeni_surum_eskisini_silmez(self):
        ilk = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        with self.assertRaisesMessage(services.IslemHatasi, 'onay bekliyor'):
            services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        services.belge_reddet(self.koordinator, ilk, 'İmza eksik')
        ikinci = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        self.assertEqual(ikinci.surum, 2)
        ilk.refresh_from_db()
        self.assertEqual((ilk.durum, ilk.red_gerekcesi), (BelgeDurumu.REDDEDILDI, 'İmza eksik'))
        self.assertEqual(len(self.diskteki_dosyalar()), 2)

    def test_farkli_donemin_transkripti_ayri_belgedir(self):
        services.belge_yukle(self.ogr, BelgeTuru.TRANSKRIPT, dosya(), donem=self.donem)
        belge = services.belge_yukle(self.ogr, BelgeTuru.TRANSKRIPT, dosya(), donem=self.donem2)
        self.assertEqual(belge.surum, 1)

    def test_onay_ve_ret_kurallari(self):
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        with self.assertRaises(services.IslemHatasi):
            services.belge_reddet(self.koordinator, belge, '  ')
        services.belge_onayla(self.koordinator, belge)
        self.assertEqual(belge.inceleyen, self.koordinator)
        with self.assertRaisesMessage(services.IslemHatasi, 'Yalnızca onay bekleyen'):
            services.belge_reddet(self.koordinator, belge, 'Geç kaldı')

    def test_roller(self):
        with self.assertRaises(PermissionDenied):
            services.belge_yukle(self.koordinator, BelgeTuru.KAYIT_FORMU, dosya())
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        for kullanici in (self.ogr, self.baskan):
            with self.assertRaises(PermissionDenied):
                services.belge_onayla(kullanici, belge)

    def test_belge_silinemez(self):
        belge = services.belge_yukle(self.ogr, BelgeTuru.KAYIT_FORMU, dosya())
        with self.assertRaises(SilmeYasak):
            belge.delete()


class BelgeEkranTest(GeciciDepo, TestVerisi, TestCase):
    def setUp(self):
        super().setUp()
        self.belge = services.belge_yukle(self.ogrenci_a.kullanici, BelgeTuru.KAYIT_FORMU, dosya('kayit.pdf'))

    def test_ogrenci_sayfadan_yukler(self):
        self.client.force_login(self.ogrenci_b.kullanici)
        cevap = self.client.post(reverse('belgelerim'), {
            'tur': BelgeTuru.TRANSKRIPT, 'donem': self.donem.pk, 'dosya': dosya('transkript.pdf'),
        }, follow=True)
        self.assertContains(cevap, 'yüklendi')
        self.assertContains(cevap, 'transkript.pdf')
        self.assertTrue(self.ogrenci_b.belgeler.filter(tur=BelgeTuru.TRANSKRIPT).exists())

    def test_sayfada_hatali_dosya_mesaji(self):
        self.client.force_login(self.ogrenci_b.kullanici)
        cevap = self.client.post(reverse('belgelerim'), {
            'tur': BelgeTuru.KAYIT_FORMU, 'dosya': dosya('virus.pdf', EXE),
        })
        self.assertContains(cevap, 'Yalnızca PDF, JPG veya PNG')
        self.assertFalse(self.ogrenci_b.belgeler.exists())

    def test_ogrenci_kendi_belgesini_indirir(self):
        self.client.force_login(self.ogrenci_a.kullanici)
        cevap = self.client.get(reverse('belge_dosyasi', args=[self.belge.pk]))
        self.assertEqual(cevap.status_code, 200)
        self.assertEqual(b''.join(cevap.streaming_content), PDF)
        self.assertEqual(cevap['Content-Type'], 'application/pdf')
        self.assertEqual(cevap['X-Content-Type-Options'], 'nosniff')

    def test_baska_ogrenci_belgeyi_acamaz(self):
        self.client.force_login(self.ogrenci_b.kullanici)
        self.assertEqual(self.client.get(reverse('belge_dosyasi', args=[self.belge.pk])).status_code, 403)

    def test_giris_yapmayan_acamaz(self):
        cevap = self.client.get(reverse('belge_dosyasi', args=[self.belge.pk]))
        self.assertEqual(cevap.status_code, 302)
        self.assertIn(reverse('giris'), cevap['Location'])

    def test_baskan_ve_koordinator_belgeyi_gorur(self):
        for kullanici in (self.baskan, self.koordinator):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('belge_dosyasi', args=[self.belge.pk])).status_code, 200)
            self.assertContains(self.client.get(reverse('ogrenci_detay', args=[self.ogrenci_a.pk])), 'kayit.pdf')

    def test_koordinator_listeden_onaylar(self):
        self.client.force_login(self.koordinator)
        self.assertContains(self.client.get(reverse('belgeler')), 'kayit.pdf')
        self.client.post(reverse('belge_onayla', args=[self.belge.pk]))
        self.belge.refresh_from_db()
        self.assertEqual(self.belge.durum, BelgeDurumu.ONAYLANDI)

    def test_baskan_ve_ogrenci_onaylayamaz(self):
        islem_sayisi = IslemKaydi.objects.count()
        for kullanici in (self.baskan, self.ogrenci_a.kullanici):
            self.client.force_login(kullanici)
            self.assertEqual(self.client.get(reverse('belgeler')).status_code, 403)
            self.assertEqual(self.client.post(reverse('belge_onayla', args=[self.belge.pk])).status_code, 403)
            cevap = self.client.post(reverse('belge_reddet', args=[self.belge.pk]), {'gerekce': 'x'})
            self.assertEqual(cevap.status_code, 403)
        self.belge.refresh_from_db()
        self.assertEqual(self.belge.durum, BelgeDurumu.BEKLIYOR)
        self.assertEqual(IslemKaydi.objects.count(), islem_sayisi)
