"""Yönerge kurallarının kontrolü. Veri yazmaz; yalnızca bulgu üretir (kayıt işi services'te).

- Eşikler koda gömülmez: hepsi KuralAyari'nin güncel sürümünden okunur. Kullanılan her ayarın değeri ve
  sürümü bulguya yazılır; böylece kural sonradan değişse de geçmiş kontrol neye göre yapıldığını saklar.
- Yalnızca onaylı kayıtlar hesaba girer (onaylı denemeler; GANO'yu zaten yalnızca koordinatör girer).
- Gerekli bir ayar yoksa o kontrol atlanır (ör. henüz ayar girilmemiş yeni kurulum).
- Bulgu karar değildir; kararı koordinatör verir.

Yorum notları (yönerge metni ikiye yorumlanabildiği yerler, tasarım açıklamasında da belirtildi):
- ÇAP Md 9e "bir defaya mahsus 2.50'nin altına düşebilir; ikinci kez 2.72'nin altına düşerse kaydı silinir":
  yarıyıl sonu GANO'su 2.72 altında olan dönemler sayılır; ikinci dönemde (veya alt sınırın da altında
  kalınırsa ilk seferde) kayıt silme uyarısı verilir.
- Yandal ortalaması: her dersin en son notlanan onaylı denemesi, AKTS ağırlıklı; harf katsayıları ayardan.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    AkademikDonem, DenemeDurumu, DonemTuru, HarfNotu, KuralAyari, ProgramTuru, UyariSeviyesi,
)

KRITIK, UYARI, BILGI = UyariSeviyesi.KRITIK, UyariSeviyesi.UYARI, UyariSeviyesi.BILGI
DERS_ALINMIS_DURUMLAR = {DenemeDurumu.ALINDI, DenemeDurumu.GECTI, DenemeDurumu.KALDI}
DONEM_SIRASI = [DonemTuru.GUZ, DonemTuru.BAHAR, DonemTuru.YAZ]
KATSAYI_ANAHTARI = 'not.katsayi.{}'


@dataclass
class Bulgu:
    kod: str
    seviye: str
    mesaj: str
    madde: str
    kurallar: dict = field(default_factory=dict)
    olcum: dict = field(default_factory=dict)


class _AyarYok(Exception):
    pass


class _Ayarlar:
    """Güncel kural ayarlarını okur; okunanları (değer + sürüm) bulguya yazmak için toplar."""

    def __init__(self):
        self.kullanilan = {}

    def al(self, anahtar):
        ayar = KuralAyari.guncel(anahtar)
        if ayar is None:
            raise _AyarYok(anahtar)
        self.kullanilan[anahtar] = {'deger': str(ayar.deger), 'surum': ayar.surum, 'madde': ayar.madde}
        return ayar.deger


# ---------------------------------------------------------------------------
# Ölçümler
# ---------------------------------------------------------------------------

def donem_sirasi(yil, tur):
    return yil, DONEM_SIRASI.index(tur)


def donem_metni(sira):
    yil, i = sira
    return str(AkademikDonem(baslangic_yili=yil, donem=DONEM_SIRASI[i]))


def tamamlanmis_donemler(ogrenci, tarih):
    """Kabul döneminden içinde bulunulan döneme kadar (hariç) geçen Güz ve Bahar dönemleri, eskiden yeniye."""
    from .services import donem_tarihten  # döngüsel içe aktarmayı önlemek için burada
    simdi = donem_sirasi(*donem_tarihten(tarih))
    yil, i = ogrenci.kabul_donemi.sira
    i = min(i, 1)  # yaz okulunda kabul edilen öğrenci için sayım bir sonraki dönemden başlar gibi davranır
    sonuc = []
    while (yil, i) < simdi:
        sonuc.append((yil, i))
        yil, i = (yil, 1) if i == 0 else (yil + 1, 0)
    return sonuc


def donem_ganolari(ogrenci):
    """Her dönemin en son girilen (iptal edilmemiş) ana dal GANO'su: [(dönem sırası, GANO), ...]."""
    son = {}
    for kayit in ogrenci.gano_kayitlari.filter(iptal=False).select_related('donem').order_by('olusturulma'):
        son[kayit.donem.sira] = kayit.gano
    return sorted(son.items())


def _kalemler(ogrenci):
    return list(ogrenci.ders_listesi.filter(listede=True).select_related('ders').prefetch_related('denemeler__donem'))


def harf_katsayilari(ayarlar):
    return {harf: ayarlar.al(KATSAYI_ANAHTARI.format(harf)) for harf in HarfNotu.values}


def program_ortalamasi(kalemler, katsayilar, kadar=None):
    """ÇAP/YDP programı ağırlıklı not ortalaması (AKTS ağırlıklı, 2 basamak). Not yoksa None.

    Her dersin `kadar` dönemine kadarki en son notlanan onaylı denemesi alınır (tekrar edilen derste son not).
    """
    toplam = akts = Decimal('0')
    for kalem in kalemler:
        notlu = [d for d in kalem.onayli_denemeler
                 if d.durum in (DenemeDurumu.GECTI, DenemeDurumu.KALDI) and d.harf_notu
                 and (kadar is None or d.donem.sira <= kadar)]
        if not notlu:
            continue
        son = max(notlu, key=lambda d: (d.donem.sira, d.olusturulma))
        toplam += katsayilar[son.harf_notu] * kalem.ders.akts
        akts += kalem.ders.akts
    if not akts:
        return None
    return (toplam / akts).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Kontroller
# ---------------------------------------------------------------------------

def _cap_gano(ogrenci, a, **_):
    ganolar = donem_ganolari(ogrenci)
    if not ganolar:
        return None
    esik, alt = a.al('cap.gano_kayit_silme'), a.al('cap.gano_alt_sinir')
    son_sira, son = ganolar[-1]
    altinda = [donem_metni(s) for s, g in ganolar if g < esik]
    olcum = {'son_gano': str(son), 'donem': donem_metni(son_sira), 'esik_alti_donemler': altinda}
    if son < alt:
        return KRITIK, (f'Ana dal GANO {son} ({donem_metni(son_sira)}): bir defalık alt sınır {alt} değerinin de '
                        f'altında. Yönergeye göre ÇAP kaydının silinmesi gerekir.'), olcum
    if son < esik and len(altinda) >= 2:
        return KRITIK, (f'Ana dal GANO ikinci kez {esik} altında ({", ".join(altinda)}). Yönergeye göre ÇAP '
                        f'kaydının silinmesi gerekir.'), olcum
    if son < esik:
        return UYARI, (f'Ana dal GANO {son} < {esik} ({donem_metni(son_sira)}): bir defalık hak kullanıldı. '
                       f'Bir daha {esik} altına düşerse kaydı silinir.'), olcum
    if altinda:
        return BILGI, (f'Bir defalık GANO hakkı daha önce kullanıldı ({", ".join(altinda)}). Bir daha {esik} '
                       f'altına düşerse kaydı silinir.'), olcum
    return None


def _ders_almama(ogrenci, a, tarih, anahtar, **_):
    sinir = int(a.al(anahtar))
    kalemler = _kalemler(ogrenci)
    if kalemler and all(k.tamamlandi for k in kalemler):
        return None  # bitirmiş öğrenci için ders almama uyarısı anlamsız
    alinan = {d.donem.sira for k in kalemler for d in k.onayli_denemeler if d.durum in DERS_ALINMIS_DURUMLAR}
    seri = []
    for sira in reversed(tamamlanmis_donemler(ogrenci, tarih)):
        if sira in alinan:
            break
        seri.append(donem_metni(sira))
    olcum = {'ders_alinmayan_donemler': list(reversed(seri))}
    if len(seri) >= sinir:
        return KRITIK, (f'Üst üste {len(seri)} dönem ders alınmamış ({", ".join(reversed(seri))}). Mazeretle kaydı '
                        f'dondurulmadıysa yönergeye göre kaydı silinir.'), olcum
    if seri and len(seri) == sinir - 1:
        return UYARI, (f'{seri[0]} döneminde ders alınmamış. Bir dönem daha ders alınmazsa kaydı silinir.'), olcum
    return None


def _azami_sure(ogrenci, a, tarih, **_):
    sure = a.al('cap.azami_sure_yil')
    yil, i = ogrenci.kabul_donemi.sira
    baslangic = datetime.date(yil + (i > 0), [9, 2, 7][i], 1)
    gecen = Decimal(str(round((tarih - baslangic).days / 365.25, 1)))
    olcum = {'gecen_yil': str(gecen), 'azami_yil': str(sure)}
    if gecen >= sure:
        return KRITIK, f'Azami öğrenim süresi ({sure} yıl) doldu: kabulden bu yana {gecen} yıl.', olcum
    if gecen >= sure - 1:
        return UYARI, f'Azami öğrenim süresinin ({sure} yıl) son yılı: kabulden bu yana {gecen} yıl.', olcum
    return None


def _cap_mezuniyet(ogrenci, a, **_):
    kalemler = _kalemler(ogrenci)
    if not kalemler or not all(k.tamamlandi for k in kalemler):
        return None
    gerekli = a.al('cap.mezuniyet_gano')
    ganolar = donem_ganolari(ogrenci)
    son = ganolar[-1][1] if ganolar else None
    olcum = {'son_gano': str(son) if son is not None else None, 'ders_sayisi': len(kalemler)}
    if son is not None and son >= gerekli:
        return BILGI, (f'Protokoldeki tüm dersler tamamlandı ve ana dal GANO {son} ≥ {gerekli}: mezuniyet şartları '
                       f'sağlanıyor. Ana dal programından mezuniyet ayrıca teyit edilmeli (Md 8ç).'), olcum
    return UYARI, (f'Protokoldeki tüm dersler tamamlandı ancak ana dal GANO '
                   f'{"girilmemiş" if son is None else f"{son} < {gerekli}"}: ÇAP diploması için şart sağlanmıyor.'), olcum


def _ydp_ders_plani(ogrenci, a, **_):
    min_akts, min_ders = a.al('ydp.min_akts'), int(a.al('ydp.min_ders_sayisi'))
    kalemler = _kalemler(ogrenci)
    akts = sum(k.ders.akts for k in kalemler)
    olcum = {'akts': akts, 'ders_sayisi': len(kalemler)}
    if akts < min_akts or len(kalemler) < min_ders:
        return UYARI, (f'Yandal ders planı yönerge alt sınırının altında: {len(kalemler)} ders / {akts} AKTS '
                       f'(en az {min_ders} ders ve {min_akts} AKTS gerekir).'), olcum
    return None


def _ydp_ana_dal_gano(ogrenci, a, **_):
    ganolar = donem_ganolari(ogrenci)
    if not ganolar:
        return None
    esik = a.al('ydp.ana_dal_gano_uyari')
    sira, son = ganolar[-1]
    if son < esik:
        return KRITIK, (f'Ana dal GANO {son} < {esik} ({donem_metni(sira)}). Yönergeye göre yandal kaydının '
                        f'silinmesi gerekir.'), {'son_gano': str(son), 'donem': donem_metni(sira)}
    return None


def _ydp_yandal_gano(ogrenci, a, tarih, **_):
    esik = a.al('ydp.yandal_gano_uyari')
    katsayilar = harf_katsayilari(a)
    kalemler = _kalemler(ogrenci)
    donemler = tamamlanmis_donemler(ogrenci, tarih)
    ortalamalar = [(s, program_ortalamasi(kalemler, katsayilar, kadar=s)) for s in donemler]
    ortalamalar = [(s, o) for s, o in ortalamalar if o is not None]
    seri = []
    for sira, ort in reversed(ortalamalar):
        if ort >= esik:
            break
        seri.append(f'{donem_metni(sira)}: {ort}')
    olcum = {'esik_alti_donemler': list(reversed(seri))}
    if len(seri) >= 2:
        return KRITIK, (f'Yandal ortalaması üst üste {len(seri)} dönem {esik} altında '
                        f'({"; ".join(reversed(seri))}). Yönergeye göre yandal kaydının silinmesi gerekir.'), olcum
    if seri:
        return UYARI, (f'Yandal ortalaması {seri[0]} — {esik} altında. Bir dönem daha altında kalırsa kaydı '
                       f'silinir.'), olcum
    return None


def _ydp_sertifika(ogrenci, a, **_):
    kalemler = _kalemler(ogrenci)
    if not kalemler or not all(k.tamamlandi for k in kalemler):
        return None
    gerekli = a.al('ydp.sertifika_gano')
    ort = program_ortalamasi(kalemler, harf_katsayilari(a))
    olcum = {'yandal_ortalamasi': str(ort) if ort is not None else None}
    if ort is not None and ort >= gerekli:
        return BILGI, (f'Yandal programındaki tüm dersler tamamlandı ve yandal ortalaması {ort} ≥ {gerekli}: '
                       f'sertifika şartları sağlanıyor. Ana dal programından mezuniyet ayrıca teyit edilmeli.'), olcum
    return UYARI, (f'Yandal dersleri tamamlandı ancak yandal ortalaması {ort} < {gerekli}: sertifika şartı '
                   f'sağlanmıyor.'), olcum


# (kod, kontrol, madde, ek parametreler)
KONTROLLER = {
    ProgramTuru.CAP: [
        ('cap.gano', _cap_gano, 'ÇAP Md 9e', {}),
        ('cap.ders_almama', _ders_almama, 'ÇAP Md 9d', {'anahtar': 'cap.ders_almama_donem'}),
        ('cap.azami_sure', _azami_sure, 'ÇAP Md 8d, 9g', {}),
        ('cap.mezuniyet', _cap_mezuniyet, 'ÇAP Md 8c', {}),
    ],
    ProgramTuru.YDP: [
        ('ydp.ders_plani', _ydp_ders_plani, 'YDP Md 5g', {}),
        ('ydp.ders_almama', _ders_almama, 'YDP Md 7-4', {'anahtar': 'ydp.ders_almama_donem'}),
        ('ydp.ana_dal_gano', _ydp_ana_dal_gano, 'YDP Md 7-5', {}),
        ('ydp.yandal_gano', _ydp_yandal_gano, 'YDP Md 7-6', {}),
        ('ydp.sertifika', _ydp_sertifika, 'YDP Md 7-8', {}),
    ],
}


def kontrol_et(ogrenci, tarih):
    """Öğrencinin programına ait tüm kontrolleri çalıştırır: [Bulgu, ...]."""
    bulgular = []
    for kod, kontrol, madde, ek in KONTROLLER[ogrenci.program_turu]:
        ayarlar = _Ayarlar()
        try:
            sonuc = kontrol(ogrenci, ayarlar, tarih=tarih, **ek)
        except _AyarYok:
            continue
        if sonuc:
            seviye, mesaj, olcum = sonuc
            bulgular.append(Bulgu(kod, seviye, mesaj, madde, ayarlar.kullanilan, olcum))
    return bulgular


def ogrenci_program_ortalamasi(ogrenci):
    """Ekranda gösterilecek ÇAP/YDP programı not ortalaması. Katsayı ayarları yoksa None."""
    try:
        katsayilar = harf_katsayilari(_Ayarlar())
    except _AyarYok:
        return None
    return program_ortalamasi(_kalemler(ogrenci), katsayilar)
