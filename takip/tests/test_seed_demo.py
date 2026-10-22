"""seed_demo komutunun beklenen demo verisini kurduğunu ve tekrar çalıştırılabildiğini doğrular."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from hesaplar.models import Kullanici
from takip.management.commands.seed_demo import DEMO_SIFRE
from takip.models import (
    Belge, BelgeDurumu, DersDenemesi, DersTalebi, IslemKaydi, KuralAyari, Ogrenci, OnayDurumu, Protokol, ProgramTuru,
    TalepDurumu,
)


def _seed():
    call_command('seed_demo', stdout=StringIO())


@override_settings(DEBUG=True)
class SeedDemoTest(TestCase):
    @classmethod
    def setUpClass(cls):
        # Demo belgesi gerçek korumali_dosyalar klasörüne değil geçici klasöre yazılır.
        cls.depo_koku = Path(tempfile.mkdtemp())
        cls.depo_ayari = override_settings(KORUMALI_DOSYA_KOKU=cls.depo_koku)
        cls.depo_ayari.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.depo_ayari.disable()
        shutil.rmtree(cls.depo_koku, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        with override_settings(DEBUG=True):
            _seed()

    def test_cap_protokolu_135_akts(self):
        protokol = Protokol.objects.get(program_turu=ProgramTuru.CAP)
        satirlar = protokol.dersler.select_related('ders')
        self.assertEqual(sum(s.ders.akts for s in satirlar), 135)
        self.assertEqual(satirlar.filter(ders__kod='TS5').count(), 3)

    def test_ydp_protokolu_yonerge_alt_sinirini_karsilar(self):
        satirlar = Protokol.objects.get(program_turu=ProgramTuru.YDP).dersler.select_related('ders')
        self.assertGreaterEqual(sum(s.ders.akts for s in satirlar), 30)
        self.assertGreaterEqual(satirlar.count(), 6)

    def test_kural_ayarlari(self):
        self.assertEqual(KuralAyari.objects.count(), 13)
        self.assertEqual(str(KuralAyari.guncel('cap.mezuniyet_gano').deger), '2.72')

    def test_ogrenciler_ve_ders_gecmisi(self):
        self.assertEqual(Ogrenci.objects.filter(program_turu=ProgramTuru.CAP).count(), 2)
        self.assertEqual(Ogrenci.objects.filter(program_turu=ProgramTuru.YDP).count(), 2)
        elif_ = Ogrenci.objects.get(ogrenci_no='24330101')
        self.assertEqual(elif_.ders_ozeti()['tamamlanan_akts'], 25)
        self.assertEqual(elif_.gano_kayitlari.count(), 3)
        # Kaldığı ders iki denemeyle görünür: eski KALDI (onaylı) + bu dönem ALINDI (bekliyor).
        denemeler = DersDenemesi.objects.filter(liste_kalemi__ogrenci=elif_, liste_kalemi__ders__kod='3301354')
        self.assertEqual(sorted(denemeler.values_list('onay_durumu', flat=True)),
                         [OnayDurumu.BEKLIYOR, OnayDurumu.ONAYLANDI])

    def test_ogrenci_girisleri_onay_bekler(self):
        self.assertEqual(DersDenemesi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).count(), 4)

    def test_bekleyen_demo_belgesi(self):
        belge = Belge.objects.get()
        self.assertEqual((belge.ogrenci.ogrenci_no, belge.durum), ('24330101', BelgeDurumu.BEKLIYOR))
        self.assertEqual(belge.mime_turu, 'application/pdf')
        self.assertTrue((self.depo_koku / belge.dosya_yolu).is_file())

    def test_bekleyen_ders_talebi(self):
        talep = DersTalebi.objects.get()
        self.assertEqual((talep.ogrenci.ogrenci_no, talep.ders.kod), ('25330201', '3301753'))
        self.assertEqual(talep.durum, TalepDurumu.BEKLIYOR)

    def test_her_sey_islem_kaydina_duser(self):
        self.assertEqual(IslemKaydi.objects.filter(islem='ogrenci_ekle').count(), 4)
        self.assertTrue(IslemKaydi.objects.filter(islem='liste_ders_cikar').exists())

    def test_demo_hesaplariyla_giris(self):
        for kullanici_adi, hedef in [('koordinator', 'ana_sayfa'), ('baskan', 'ana_sayfa'), ('24330101', 'benim')]:
            cevap = self.client.post(reverse('giris'), {'username': kullanici_adi, 'password': DEMO_SIFRE},
                                     follow=True)
            self.assertEqual(cevap.redirect_chain[-1][0], reverse(hedef), kullanici_adi)
            self.client.post(reverse('cikis'))

    def test_tekrar_calistirinca_cogaltmaz(self):
        onceki = (Kullanici.objects.count(), Ogrenci.objects.count(), DersDenemesi.objects.count(),
                  KuralAyari.objects.count(), IslemKaydi.objects.count())
        _seed()
        sonraki = (Kullanici.objects.count(), Ogrenci.objects.count(), DersDenemesi.objects.count(),
                   KuralAyari.objects.count(), IslemKaydi.objects.count())
        self.assertEqual(onceki, sonraki)


class SeedDemoGuvenlikTest(TestCase):
    @override_settings(DEBUG=False)
    def test_debug_kapaliyken_calismaz(self):
        with self.assertRaises(CommandError):
            _seed()
        self.assertFalse(Kullanici.objects.filter(username='koordinator').exists())

    @override_settings(DEBUG=False)
    def test_canli_bayragiyla_debug_kapaliyken_calisir(self):
        depo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, depo, ignore_errors=True)
        with override_settings(KORUMALI_DOSYA_KOKU=depo):
            call_command('seed_demo', '--canli', stdout=StringIO())
        self.assertTrue(Kullanici.objects.get(username='koordinator').check_password(DEMO_SIFRE))
