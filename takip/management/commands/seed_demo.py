"""Demo verisini yükler: katalog, protokoller, kural ayarları, demo hesapları ve öğrenciler.

Kullanım:
    python manage.py migrate
    python manage.py seed_demo

- Tüm veri takip.services üzerinden girilir; her adım İşlem Kaydı'na düşer.
- Tekrar çalıştırılabilir: var olan ders / protokol / ayar / hesap / öğrenci atlanır.
- Bilinen demo şifreleri kullandığı için yalnızca DEBUG açıkken çalışır.
- Tüm kişiler ve notlar sentetiktir.
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hesaplar.models import Kullanici, Rol
from takip import services
from takip.models import DenemeDurumu, Ders, DersTuru, KuralAyari, Ogrenci, Protokol, ProgramTuru

DEMO_SIFRE = 'Demo.2026'

# EEM → Bilgisayar Müh. ÇAP protokolü (CLAUDE.md, toplam 135 AKTS).
# Yarıyıl, ders kodunun 5. hanesidir (3301354 → 3. yarıyıl).
CAP_DERSLERI = [
    ('3301156', 'Bilgisayar Mühendisliğine Giriş', 4),
    ('3301351', 'Nesneye Yönelik Programlama Dili', 4),
    ('3301352', 'İşletim Sistemleri', 4),
    ('3301354', 'Veri Yapıları ve Uygulamaları', 4),
    ('3301452', 'Programlama Dili-2', 4),
    ('3301454', 'Veri Tabanı Yönetim Sistemleri', 5),
    ('3301455', 'Yazılım Mühendisliği', 4),
    ('3301456', 'Mobil Programlama', 4),
    ('3301552', 'Programlama Dili-3', 5),
    ('3301553', 'Veri Haberleşmesi ve Ağlar', 5),
    ('3301651', 'Yapay Zeka', 4),
    ('3301652', 'Otomata Teorisi ve Biçimsel Diller', 4),
    ('3301653', 'Görüntü İşleme', 4),
    ('3301654', 'Mühendislik Tasarımı', 6),
    ('3301751', 'Bilgisayar Mühendisliği Uygulamaları', 4),
    ('3301752', 'Bilgisayar Mimarisi ve Organizasyonu', 4),
    ('3301753', 'Veri Bilimi', 4),
    ('3301851', 'İşletmede Mesleki Eğitim', 20),
    ('3301852', 'Staj 1', 5),
    ('3301853', 'Staj 2', 5),
]

# Teknik seçmeliler: katalogda yer tutucu havuz dersi, protokolde birden çok satır.
# (kod, ad, akts, yarıyıl, protokoldeki adet)
SECMELI_HAVUZLARI = [
    ('TS5', '5. Yarıyıl Teknik Seçmeli', 4, 5, 3),
    ('TS6', '6. Yarıyıl Teknik Seçmeli', 4, 6, 3),
    ('TS7', '7. Yarıyıl Teknik Seçmeli', 4, 7, 2),
]

# Sentetik yandal protokolü: 7 ders, 30 AKTS (YDP Md 5g: en az 30 AKTS ve 6 ders).
YDP_DERSLERI = ['3301156', '3301351', '3301354', '3301452', '3301454', '3301455', '3301553']

CAP_PROTOKOL_ADI = 'EEM → Bilgisayar Müh. ÇAP'
YDP_PROTOKOL_ADI = 'Makine Müh. → Bilgisayar Müh. Yandal (sentetik)'

# (anahtar, program, değer, açıklama, yönerge maddesi)
KURAL_AYARLARI = [
    ('cap.gano_alt_sinir', ProgramTuru.CAP, '2.50', 'Ana dal GANO bir kez bu değere kadar düşebilir', '9e'),
    ('cap.gano_kayit_silme', ProgramTuru.CAP, '2.72', 'İkinci kez bu değerin altı → kayıt silme uyarısı', '9e'),
    ('cap.ders_almama_donem', ProgramTuru.CAP, '2', 'Mazeretsiz bu kadar dönem ders almama → uyarı', '9d'),
    ('cap.mezuniyet_gano', ProgramTuru.CAP, '2.72', 'Mezuniyet için en az ana dal GANO', '8c'),
    ('cap.toplam_akts', ProgramTuru.CAP, '240', 'Toplam AKTS', '7-2'),
    ('cap.azami_sure_yil', ProgramTuru.CAP, '7', 'Azami süre (yıl)', '8d'),
    ('ydp.min_akts', ProgramTuru.YDP, '30', 'En az AKTS', '5g'),
    ('ydp.min_ders_sayisi', ProgramTuru.YDP, '6', 'En az ders sayısı', '5g'),
    ('ydp.ders_almama_donem', ProgramTuru.YDP, '2', 'Bu kadar dönem ders almama → uyarı', '7-4'),
    ('ydp.ana_dal_gano_uyari', ProgramTuru.YDP, '2.30', 'Ana dal GANO bu değerin altı → uyarı', '7-5'),
    ('ydp.yandal_gano_uyari', ProgramTuru.YDP, '2.00', 'Yandal GANO iki dönem bu değerin altı → uyarı', '7-6'),
    ('ydp.sertifika_gano', ProgramTuru.YDP, '2.00', 'Sertifika için en az yandal GANO', '7-8'),
    ('ydp.ek_sure_yariyil', ProgramTuru.YDP, '2', 'En çok ek süre (yarıyıl)', '7-9'),
]

GANO_KAYNAGI = 'OBİS transkripti (sentetik demo verisi)'

# gecmis: koordinatörün geriye dönük girdiği onaylı dersler (yıl, dönem, kod, durum, not)
# ogrenci_girisi: öğrencinin bu dönem kendisinin girdiği, onay bekleyen kayıtlar
# cikarilan: koordinatörün gerekçeyle listeden çıkardığı dersler
OGRENCILER = [
    {
        'ogrenci_no': '24330101', 'ad': 'Elif', 'soyad': 'Yılmaz',
        'program_turu': ProgramTuru.CAP, 'ana_dal_bolumu': 'Elektrik-Elektronik Müh.',
        'protokol': CAP_PROTOKOL_ADI, 'kabul': (2024, 'GUZ'),
        'gecmis': [
            (2024, 'GUZ', '3301156', DenemeDurumu.GECTI, 'BA'),
            (2024, 'BAHAR', '3301452', DenemeDurumu.GECTI, 'BB'),
            (2024, 'BAHAR', '3301454', DenemeDurumu.GECTI, 'CB'),
            (2025, 'GUZ', '3301351', DenemeDurumu.GECTI, 'AA'),
            (2025, 'GUZ', '3301354', DenemeDurumu.KALDI, 'FF'),
            (2025, 'BAHAR', '3301455', DenemeDurumu.GECTI, 'BB'),
            (2025, 'BAHAR', '3301456', DenemeDurumu.GECTI, 'CC'),
        ],
        'gano': [(2024, 'GUZ', '3.10'), (2025, 'GUZ', '3.05'), (2025, 'BAHAR', '3.12')],
        'ogrenci_girisi': [
            (2026, 'GUZ', '3301354', DenemeDurumu.ALINDI),  # kaldığı dersi tekrar alıyor
            (2026, 'GUZ', '3301552', DenemeDurumu.ALINDI),
        ],
        'cikarilan': [],
    },
    {
        'ogrenci_no': '25330102', 'ad': 'Burak', 'soyad': 'Kaya',
        'program_turu': ProgramTuru.CAP, 'ana_dal_bolumu': 'Elektrik-Elektronik Müh.',
        'protokol': CAP_PROTOKOL_ADI, 'kabul': (2025, 'GUZ'),
        'gecmis': [
            (2025, 'GUZ', '3301156', DenemeDurumu.GECTI, 'DC'),
            (2025, 'GUZ', '3301351', DenemeDurumu.KALDI, 'FF'),
            (2025, 'BAHAR', '3301452', DenemeDurumu.GECTI, 'CC'),
            (2025, 'BAHAR', '3301553', DenemeDurumu.MUAF, ''),
        ],
        'gano': [(2025, 'GUZ', '2.65'), (2025, 'BAHAR', '2.55')],
        'ogrenci_girisi': [(2026, 'GUZ', '3301351', DenemeDurumu.PLANLANDI)],
        'cikarilan': [
            ('3301456', 'Ana dalda eşdeğer ders alındı; bölüm kurulu kararıyla çıkarıldı (sentetik).'),
        ],
    },
    {
        'ogrenci_no': '25330201', 'ad': 'Zeynep', 'soyad': 'Arslan',
        'program_turu': ProgramTuru.YDP, 'ana_dal_bolumu': 'Makine Müh.',
        'protokol': YDP_PROTOKOL_ADI, 'kabul': (2025, 'BAHAR'),
        'gecmis': [
            (2025, 'BAHAR', '3301156', DenemeDurumu.GECTI, 'BB'),
            (2025, 'BAHAR', '3301455', DenemeDurumu.GECTI, 'CB'),
        ],
        'gano': [(2025, 'BAHAR', '2.40')],
        'ogrenci_girisi': [(2026, 'GUZ', '3301351', DenemeDurumu.ALINDI)],
        'cikarilan': [],
    },
    {
        'ogrenci_no': '26330202', 'ad': 'Emre', 'soyad': 'Çelik',
        'program_turu': ProgramTuru.YDP, 'ana_dal_bolumu': 'Makine Müh.',
        'protokol': YDP_PROTOKOL_ADI, 'kabul': (2026, 'GUZ'),
        'gecmis': [], 'gano': [], 'ogrenci_girisi': [], 'cikarilan': [],
    },
]


class Command(BaseCommand):
    help = 'Demo verisini (sentetik) servis katmanı üzerinden yükler. Tekrar çalıştırılabilir.'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_demo bilinen demo şifreleri kullanır; yalnızca DEBUG açıkken çalışır.')
        # Windows'ta çıktı dosyaya/boruya yönlendirilince cp1252 Türkçe harfleri yazamaz.
        if hasattr(sys.stdout, 'reconfigure') and (sys.stdout.encoding or '').lower() != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')

        self.sayac = {'eklendi': 0, 'atlandi': 0}
        with transaction.atomic():
            koord = self._hesap('koordinator', Rol.KOORDINATOR, 'Demo', 'Koordinatör')
            self._hesap('baskan', Rol.BOLUM_BASKANI, 'Demo', 'Bölüm Başkanı')
            dersler = self._katalog(koord)
            protokoller = self._protokoller(koord, dersler)
            self._kural_ayarlari(koord)
            for veri in OGRENCILER:
                self._ogrenci(koord, protokoller, veri)

        self.stdout.write(self.style.SUCCESS(
            f"Demo verisi hazır: {self.sayac['eklendi']} kayıt eklendi, {self.sayac['atlandi']} zaten vardı."
        ))
        self.stdout.write(f'\nDemo hesapları (hepsinin şifresi: {DEMO_SIFRE})')
        self.stdout.write('  koordinator  → Koordinatör')
        self.stdout.write('  baskan       → Bölüm Başkanı')
        for veri in OGRENCILER:
            self.stdout.write(f"  {veri['ogrenci_no']:<12} → Öğrenci ({veri['ad']} {veri['soyad']}, "
                              f"{ProgramTuru(veri['program_turu']).label})")

    # -----------------------------------------------------------------------

    def _eklendi(self, eklendi):
        self.sayac['eklendi' if eklendi else 'atlandi'] += 1

    def _hesap(self, kullanici_adi, rol, ad, soyad):
        hesap = Kullanici.objects.filter(username=kullanici_adi).first()
        self._eklendi(hesap is None)
        if hesap is None:
            hesap = Kullanici.objects.create_user(
                kullanici_adi, password=DEMO_SIFRE, rol=rol, first_name=ad, last_name=soyad,
            )
        elif hesap.rol != rol:
            raise CommandError(f"'{kullanici_adi}' hesabı var ama rolü {hesap.rol}; seed devam edemez.")
        return hesap

    def _ders(self, koord, kod, ad, akts, tur):
        ders = Ders.objects.filter(kod=kod).first()
        self._eklendi(ders is None)
        return ders or services.katalog_dersi_ekle(koord, kod, ad, akts, tur)

    def _katalog(self, koord):
        dersler = {}
        for kod, ad, akts in CAP_DERSLERI:
            dersler[kod] = self._ders(koord, kod, ad, akts, DersTuru.ZORUNLU)
        for kod, ad, akts, _, _ in SECMELI_HAVUZLARI:
            dersler[kod] = self._ders(koord, kod, ad, akts, DersTuru.SECMELI_HAVUZ)
        return dersler

    def _protokoller(self, koord, dersler):
        cap_satirlari = [(dersler[kod], int(kod[4])) for kod, _, _ in CAP_DERSLERI]
        for kod, _, _, yariyil, adet in SECMELI_HAVUZLARI:
            cap_satirlari += [(dersler[kod], yariyil)] * adet
        cap_satirlari.sort(key=lambda satir: satir[1])
        ydp_satirlari = [(dersler[kod], int(kod[4])) for kod in YDP_DERSLERI]

        protokoller = {}
        for ad, program, ana_dal, satirlar in [
            (CAP_PROTOKOL_ADI, ProgramTuru.CAP, 'Elektrik-Elektronik Müh.', cap_satirlari),
            (YDP_PROTOKOL_ADI, ProgramTuru.YDP, 'Makine Müh.', ydp_satirlari),
        ]:
            protokol = Protokol.objects.filter(ad=ad).first()
            self._eklendi(protokol is None)
            protokoller[ad] = protokol or services.protokol_ekle(koord, ad, program, ana_dal, satirlar)
        return protokoller

    def _kural_ayarlari(self, koord):
        # Var olan ayara dokunulmaz: koordinatör değiştirdiyse seed onu eski değere döndürmesin.
        for anahtar, program, deger, aciklama, madde in KURAL_AYARLARI:
            yok = KuralAyari.guncel(anahtar) is None
            self._eklendi(yok)
            if yok:
                services.kural_ayari_belirle(koord, anahtar, program, deger, aciklama, madde)

    def _ogrenci(self, koord, protokoller, veri):
        if Ogrenci.objects.filter(ogrenci_no=veri['ogrenci_no']).exists():
            self._eklendi(False)
            return
        self._eklendi(True)

        donem = lambda yil, tur: services.donem_bul_veya_ekle(koord, yil, tur)  # noqa: E731
        ogrenci, _ = services.ogrenci_ekle(
            koord,
            ogrenci_no=veri['ogrenci_no'], ad=veri['ad'], soyad=veri['soyad'],
            okul_eposta=f"{veri['ogrenci_no']}@ogr.example.edu.tr",
            program_turu=veri['program_turu'], ana_dal_bolumu=veri['ana_dal_bolumu'],
            protokol=protokoller[veri['protokol']], kabul_donemi=donem(*veri['kabul']),
            sifre=DEMO_SIFRE,
        )
        kalem = lambda kod: ogrenci.ders_listesi.get(ders__kod=kod, listede=True)  # noqa: E731

        for yil, tur, kod, durum, harf_notu in veri['gecmis']:
            services.deneme_ekle(koord, kalem(kod), donem(yil, tur), durum, harf_notu, geriye_donuk=True)
        for yil, tur, gano in veri['gano']:
            services.ana_dal_gano_gir(koord, ogrenci, donem(yil, tur), gano, GANO_KAYNAGI)
        for kod, gerekce in veri['cikarilan']:
            services.listeden_ders_cikar(koord, kalem(kod), gerekce)
        for yil, tur, kod, durum in veri['ogrenci_girisi']:
            services.deneme_ekle(ogrenci.kullanici, kalem(kod), donem(yil, tur), durum)
