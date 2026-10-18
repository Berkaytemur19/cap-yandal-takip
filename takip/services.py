"""Servis katmanı: veriyi değiştiren TÜM işlemler buradan geçer.

- Ekranlar, seed komutu ve ileride CSV/OBİS içe aktarma bu fonksiyonları çağırır.
- Her fonksiyon yetkiyi kendisi de kontrol eder (view'daki kontrole ek olarak).
- Her değişiklik IslemKaydi'na kim / ne / eski / yeni olarak yazılır.
- İş kuralı ihlalinde IslemHatasi fırlatılır; view bunu kullanıcıya mesaj olarak gösterir.
"""

import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from hesaplar.models import Rol

from .models import (
    AkademikDonem, AnaDalGanoKaydi, DenemeDurumu, Ders, DersDenemesi, IslemKaydi,
    KuralAyari, Ogrenci, OgrenciDers, OnayDurumu, Protokol, ProtokolDersi,
)


class IslemHatasi(Exception):
    """Kullanıcıya gösterilebilecek iş kuralı hatası."""


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _deger(nesne, alanlar):
    """Nesnenin seçili alanlarını işlem kaydı için JSON'a uygun sözlüğe çevirir."""
    sonuc = {}
    for alan in alanlar:
        v = getattr(nesne, alan)
        sonuc[alan] = None if v is None else str(v)
    return sonuc


def islem_kaydet(kullanici, islem, nesne, eski=None, yeni=None, aciklama=''):
    return IslemKaydi.objects.create(
        kullanici=kullanici,
        islem=islem,
        model_adi=type(nesne).__name__,
        nesne_id=str(nesne.pk),
        nesne_metni=str(nesne)[:300],
        eski_deger=eski,
        yeni_deger=yeni,
        aciklama=aciklama,
    )


def _koordinator_olmali(kullanici):
    if kullanici is None or kullanici.rol != Rol.KOORDINATOR:
        raise PermissionDenied('Bu işlemi yalnızca koordinatör yapabilir.')


def _gerekce_olmali(gerekce):
    if not (gerekce or '').strip():
        raise IslemHatasi('Gerekçe yazılması zorunludur.')


# ---------------------------------------------------------------------------
# Dönem ve katalog
# ---------------------------------------------------------------------------

def donem_bul_veya_ekle(kullanici, baslangic_yili, donem):
    _koordinator_olmali(kullanici)
    nesne, yeni = AkademikDonem.objects.get_or_create(baslangic_yili=baslangic_yili, donem=donem)
    if yeni:
        islem_kaydet(kullanici, 'donem_ekle', nesne, yeni=_deger(nesne, ['baslangic_yili', 'donem']))
    return nesne


DERS_ALANLARI = ['kod', 'ad', 'akts', 'tur', 'aktif']


@transaction.atomic
def katalog_dersi_ekle(kullanici, kod, ad, akts, tur):
    _koordinator_olmali(kullanici)
    kod = kod.strip()
    if Ders.objects.filter(kod=kod).exists():
        raise IslemHatasi(f'{kod} kodlu ders katalogda zaten var.')
    ders = Ders.objects.create(kod=kod, ad=ad.strip(), akts=akts, tur=tur)
    islem_kaydet(kullanici, 'katalog_ders_ekle', ders, yeni=_deger(ders, DERS_ALANLARI))
    return ders


@transaction.atomic
def katalog_dersi_guncelle(kullanici, ders, ad, akts, tur):
    """Ders kodu değiştirilemez (benzersiz anahtar). Ad, AKTS ve tür güncellenebilir."""
    _koordinator_olmali(kullanici)
    eski = _deger(ders, DERS_ALANLARI)
    ders.ad, ders.akts, ders.tur = ad.strip(), akts, tur
    ders.save()
    yeni = _deger(ders, DERS_ALANLARI)
    if eski != yeni:
        islem_kaydet(kullanici, 'katalog_ders_guncelle', ders, eski=eski, yeni=yeni)
    return ders


@transaction.atomic
def katalog_dersi_aktiflik(kullanici, ders, aktif):
    """Ders silinmez; pasife alınır veya yeniden aktifleştirilir."""
    _koordinator_olmali(kullanici)
    if ders.aktif == aktif:
        return ders
    eski = _deger(ders, ['aktif'])
    ders.aktif = aktif
    ders.save()
    islem_kaydet(
        kullanici, 'katalog_ders_aktif' if aktif else 'katalog_ders_pasif', ders,
        eski=eski, yeni=_deger(ders, ['aktif']),
    )
    return ders


@transaction.atomic
def protokol_ekle(kullanici, ad, program_turu, ana_dal_bolumu, dersler):
    """dersler: [(Ders, yarıyıl), ...]. Seçmeli havuz dersi birden çok kez yer alabilir."""
    _koordinator_olmali(kullanici)
    protokol = Protokol.objects.create(ad=ad, program_turu=program_turu, ana_dal_bolumu=ana_dal_bolumu)
    for ders, yariyil in dersler:
        ProtokolDersi.objects.create(protokol=protokol, ders=ders, yariyil=yariyil)
    islem_kaydet(
        kullanici, 'protokol_ekle', protokol,
        yeni={**_deger(protokol, ['ad', 'program_turu', 'ana_dal_bolumu']),
              'dersler': [f'{d.kod} (yy {y})' for d, y in dersler]},
    )
    return protokol


# ---------------------------------------------------------------------------
# Öğrenci
# ---------------------------------------------------------------------------

OGRENCI_ALANLARI = [
    'ogrenci_no', 'ad', 'soyad', 'okul_eposta', 'program_turu',
    'ana_dal_bolumu', 'protokol', 'kabul_donemi', 'kayit_durumu',
]


@transaction.atomic
def ogrenci_ekle(kullanici, *, ogrenci_no, ad, soyad, okul_eposta, program_turu,
                 ana_dal_bolumu, protokol, kabul_donemi, sifre=None):
    """Öğrenciyi ve giriş hesabını açar, ders listesini protokolden oluşturur.

    Dönüş: (ogrenci, sifre). Şifre verilmezse rastgele geçici şifre üretilir
    ve koordinatöre bir kez gösterilir.
    """
    _koordinator_olmali(kullanici)
    Kullanici = get_user_model()
    ogrenci_no = ogrenci_no.strip()
    okul_eposta = okul_eposta.strip().lower()

    if Ogrenci.objects.filter(ogrenci_no=ogrenci_no).exists() or \
            Kullanici.objects.filter(username=ogrenci_no).exists():
        raise IslemHatasi(f'{ogrenci_no} numaralı öğrenci zaten kayıtlı.')
    if Ogrenci.objects.filter(okul_eposta=okul_eposta).exists():
        raise IslemHatasi(f'{okul_eposta} adresi başka bir öğrencide kayıtlı.')
    if protokol.program_turu != program_turu:
        raise IslemHatasi('Seçilen protokol, öğrencinin program türüyle (ÇAP/YDP) uyuşmuyor.')

    sifre = sifre or secrets.token_urlsafe(9)
    hesap = Kullanici.objects.create_user(
        username=ogrenci_no, email=okul_eposta, password=sifre,
        first_name=ad, last_name=soyad, rol=Rol.OGRENCI,
    )
    ogrenci = Ogrenci.objects.create(
        kullanici=hesap, ogrenci_no=ogrenci_no, ad=ad.strip(), soyad=soyad.strip(),
        okul_eposta=okul_eposta, program_turu=program_turu, ana_dal_bolumu=ana_dal_bolumu,
        protokol=protokol, kabul_donemi=kabul_donemi,
    )
    islem_kaydet(kullanici, 'ogrenci_ekle', ogrenci, yeni=_deger(ogrenci, OGRENCI_ALANLARI))

    for satir in protokol.dersler.select_related('ders'):
        OgrenciDers.objects.create(
            ogrenci=ogrenci, ders=satir.ders, yariyil=satir.yariyil,
            ekleme_gerekcesi=f'Protokolden: {protokol.ad}', ekleyen=kullanici,
        )
    return ogrenci, sifre


@transaction.atomic
def ana_dal_gano_gir(kullanici, ogrenci, donem, gano, kaynak):
    _koordinator_olmali(kullanici)
    if not (kaynak or '').strip():
        raise IslemHatasi('GANO kaynağı yazılması zorunludur.')
    gano = Decimal(str(gano))
    if not Decimal('0') <= gano <= Decimal('4'):
        raise IslemHatasi('GANO 0.00 ile 4.00 arasında olmalıdır.')
    kayit = AnaDalGanoKaydi.objects.create(
        ogrenci=ogrenci, donem=donem, gano=gano, kaynak=kaynak.strip(), giren=kullanici,
    )
    islem_kaydet(kullanici, 'ana_dal_gano_gir', kayit, yeni=_deger(kayit, ['donem', 'gano', 'kaynak']))
    return kayit


# ---------------------------------------------------------------------------
# Ders listesi
# ---------------------------------------------------------------------------

@transaction.atomic
def listeye_ders_ekle(kullanici, ogrenci, ders, gerekce, yariyil=None):
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    if not ders.aktif:
        raise IslemHatasi('Pasif ders listeye eklenemez.')
    if ders.tur != 'SECMELI_HAVUZ' and ogrenci.ders_listesi.filter(ders=ders, listede=True).exists():
        raise IslemHatasi(f'{ders.kod} zaten öğrencinin ders listesinde.')
    kalem = OgrenciDers.objects.create(
        ogrenci=ogrenci, ders=ders, yariyil=yariyil, ekleme_gerekcesi=gerekce, ekleyen=kullanici,
    )
    islem_kaydet(kullanici, 'liste_ders_ekle', kalem, yeni={'ders': ders.kod}, aciklama=gerekce)
    return kalem


@transaction.atomic
def listeden_ders_cikar(kullanici, kalem, gerekce):
    """Kalem silinmez; listede=False yapılır. Geçilmiş/muaf derse dokunulmaz."""
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    if not kalem.listede:
        raise IslemHatasi('Bu ders zaten listeden çıkarılmış.')
    if kalem.tamamlandi:
        raise IslemHatasi('Geçilmiş veya muaf olunmuş ders listeden çıkarılamaz.')
    kalem.listede = False
    kalem.cikarma_gerekcesi = gerekce
    kalem.cikaran = kullanici
    kalem.cikarilma_tarihi = timezone.now()
    kalem.save()
    islem_kaydet(
        kullanici, 'liste_ders_cikar', kalem,
        eski={'listede': 'True'}, yeni={'listede': 'False'}, aciklama=gerekce,
    )
    return kalem


# ---------------------------------------------------------------------------
# Ders denemeleri
# ---------------------------------------------------------------------------

DENEME_ALANLARI = ['donem', 'durum', 'harf_notu', 'onay_durumu']

# Öğrenci şimdilik yalnızca planlama/alındı girebilir. Not girişi transkript
# yükleme özelliğiyle birlikte açılacak (transkript olmadan not onaya gönderilemez).
OGRENCININ_GIREBILECEGI_DURUMLAR = {DenemeDurumu.PLANLANDI, DenemeDurumu.ALINDI}


def _deneme_tutarliligi(durum, harf_notu):
    if durum in (DenemeDurumu.GECTI, DenemeDurumu.KALDI) and not harf_notu:
        raise IslemHatasi('Geçti/Kaldı durumunda harf notu zorunludur.')
    if durum not in (DenemeDurumu.GECTI, DenemeDurumu.KALDI) and harf_notu:
        raise IslemHatasi('Harf notu yalnızca Geçti/Kaldı durumunda girilir.')


@transaction.atomic
def deneme_ekle(kullanici, kalem, donem, durum, harf_notu='', geriye_donuk=False):
    """Öğrenci girerse 'onay bekliyor' başlar. Koordinatör girerse doğrudan onaylıdır."""
    if kullanici.rol == Rol.OGRENCI:
        if kalem.ogrenci.kullanici_id != kullanici.pk:
            raise PermissionDenied
        if durum not in OGRENCININ_GIREBILECEGI_DURUMLAR or harf_notu or geriye_donuk:
            raise IslemHatasi('Not girişi transkript yüklendikten sonra yapılabilir.')
    else:
        _koordinator_olmali(kullanici)

    _deneme_tutarliligi(durum, harf_notu)
    if not kalem.listede:
        raise IslemHatasi('Listeden çıkarılmış derse deneme eklenemez.')
    if kalem.tamamlandi:
        raise IslemHatasi('Bu ders zaten geçilmiş veya muaf.')
    if kalem.denemeler.filter(donem=donem).exclude(
            onay_durumu__in=[OnayDurumu.IPTAL, OnayDurumu.REDDEDILDI]).exists():
        raise IslemHatasi(f'Bu ders için {donem} döneminde zaten kayıt var.')

    koordinator = kullanici.rol == Rol.KOORDINATOR
    deneme = DersDenemesi.objects.create(
        liste_kalemi=kalem, donem=donem, durum=durum, harf_notu=harf_notu,
        geriye_donuk=geriye_donuk, giren=kullanici,
        onay_durumu=OnayDurumu.ONAYLANDI if koordinator else OnayDurumu.BEKLIYOR,
        onaylayan=kullanici if koordinator else None,
        onay_tarihi=timezone.now() if koordinator else None,
    )
    islem_kaydet(
        kullanici, 'deneme_ekle', deneme, yeni=_deger(deneme, DENEME_ALANLARI),
        aciklama='Geriye dönük giriş' if geriye_donuk else '',
    )
    return deneme


@transaction.atomic
def deneme_onayla(kullanici, deneme):
    _koordinator_olmali(kullanici)
    if deneme.onay_durumu != OnayDurumu.BEKLIYOR:
        raise IslemHatasi('Yalnızca onay bekleyen kayıt onaylanabilir.')
    eski = _deger(deneme, ['onay_durumu'])
    deneme.onay_durumu = OnayDurumu.ONAYLANDI
    deneme.onaylayan = kullanici
    deneme.onay_tarihi = timezone.now()
    deneme.save()
    islem_kaydet(kullanici, 'deneme_onayla', deneme, eski=eski, yeni=_deger(deneme, ['onay_durumu']))
    return deneme


@transaction.atomic
def deneme_reddet(kullanici, deneme, gerekce):
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    if deneme.onay_durumu != OnayDurumu.BEKLIYOR:
        raise IslemHatasi('Yalnızca onay bekleyen kayıt reddedilebilir.')
    eski = _deger(deneme, ['onay_durumu'])
    deneme.onay_durumu = OnayDurumu.REDDEDILDI
    deneme.red_gerekcesi = gerekce
    deneme.save()
    islem_kaydet(kullanici, 'deneme_reddet', deneme, eski=eski,
                 yeni=_deger(deneme, ['onay_durumu']), aciklama=gerekce)
    return deneme


@transaction.atomic
def deneme_duzelt(kullanici, deneme, gerekce, *, donem=None, durum=None, harf_notu=None):
    """Onaylı (kilitli) kaydı yalnızca koordinatör düzeltir; eski/yeni değer kayda geçer."""
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    if deneme.onay_durumu == OnayDurumu.IPTAL:
        raise IslemHatasi('İptal edilmiş kayıt düzeltilemez.')
    eski = _deger(deneme, DENEME_ALANLARI)
    if donem is not None:
        deneme.donem = donem
    if durum is not None:
        deneme.durum = durum
    if harf_notu is not None:
        deneme.harf_notu = harf_notu
    _deneme_tutarliligi(deneme.durum, deneme.harf_notu)
    deneme._kilit_acik = True
    deneme.save()
    islem_kaydet(kullanici, 'deneme_duzelt', deneme, eski=eski,
                 yeni=_deger(deneme, DENEME_ALANLARI), aciklama=gerekce)
    return deneme


@transaction.atomic
def deneme_iptal(kullanici, deneme, gerekce):
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    if deneme.onay_durumu == OnayDurumu.IPTAL:
        raise IslemHatasi('Kayıt zaten iptal edilmiş.')
    eski = _deger(deneme, ['onay_durumu'])
    deneme.onay_durumu = OnayDurumu.IPTAL
    deneme.iptal_gerekcesi = gerekce
    deneme._kilit_acik = True
    deneme.save()
    islem_kaydet(kullanici, 'deneme_iptal', deneme, eski=eski,
                 yeni=_deger(deneme, ['onay_durumu']), aciklama=gerekce)
    return deneme


# ---------------------------------------------------------------------------
# Kural ayarları (sürümlü)
# ---------------------------------------------------------------------------

@transaction.atomic
def kural_ayari_belirle(kullanici, anahtar, program_turu, deger, aciklama, madde):
    """Yeni sürüm ekler; eski sürümler olduğu gibi kalır. Değer aynıysa bir şey yapmaz."""
    _koordinator_olmali(kullanici)
    deger = Decimal(str(deger))
    guncel = KuralAyari.guncel(anahtar)
    if guncel and guncel.deger == deger:
        return guncel
    ayar = KuralAyari.objects.create(
        anahtar=anahtar, program_turu=program_turu, deger=deger, aciklama=aciklama,
        madde=madde, surum=(guncel.surum + 1) if guncel else 1, olusturan=kullanici,
    )
    islem_kaydet(
        kullanici, 'kural_ayari', ayar,
        eski={'deger': str(guncel.deger), 'surum': str(guncel.surum)} if guncel else None,
        yeni={'deger': str(ayar.deger), 'surum': str(ayar.surum)},
    )
    return ayar
