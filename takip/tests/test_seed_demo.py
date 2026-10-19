"""seed_demo komutunun beklenen demo verisini kurduğunu ve tekrar çalıştırılabildiğini doğrular."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from hesaplar.models import Kullanici
from takip.management.commands.seed_demo import DEMO_SIFRE
from takip.models import (
    DersDenemesi, IslemKaydi, KuralAyari, Ogrenci, OnayDurumu, Protokol, ProgramTuru,
)


def _seed():
    call_command('seed_demo', stdout=StringIO())


@override_settings(DEBUG=True)
class SeedDemoTest(TestCase):
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
