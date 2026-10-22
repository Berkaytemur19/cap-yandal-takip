"""Servis katmanı: veriyi değiştiren TÜM işlemler buradan geçer.

- Ekranlar, seed komutu ve ileride CSV/OBİS içe aktarma bu fonksiyonları çağırır.
- Her fonksiyon yetkiyi kendisi de kontrol eder (view'daki kontrole ek olarak).
- Her değişiklik IslemKaydi'na kim / ne / eski / yeni olarak yazılır.
- İş kuralı ihlalinde IslemHatasi fırlatılır; view bunu kullanıcıya mesaj olarak gösterir.
"""

import hashlib
import secrets
import uuid
from decimal import Decimal
from pathlib import Path

import magic
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils import timezone

from hesaplar.models import Rol

from .models import (
    DONEMLI_BELGE_TURLERI, OGRENCI_BELGE_TURLERI, AkademikDonem, AnaDalGanoKaydi, Belge, BelgeDurumu,
    BelgeIstegi, BelgeTuru, DenemeDurumu, Ders, DersDenemesi, DersTalebi, DersTuru, DonemTuru, HarfNotu,
    IslemKaydi, KayitDurumu, KuralAyari, Mesaj, NotGirisi, Ogrenci, OgrenciDers, OnayDurumu, Protokol,
    ProtokolDersi, TalepDurumu,
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
# Öğrencinin ders seçimi ve ders talepleri
# ---------------------------------------------------------------------------

def donem_tarihten(tarih):
    """Tarihin düştüğü akademik dönem: (başlangıç yılı, dönem türü).

    Eylül–Ocak Güz, Şubat–Haziran Bahar, Temmuz–Ağustos Yaz.
    """
    if tarih.month >= 9:
        return tarih.year, DonemTuru.GUZ
    if tarih.month == 1:
        return tarih.year - 1, DonemTuru.GUZ
    if tarih.month <= 6:
        return tarih.year - 1, DonemTuru.BAHAR
    return tarih.year - 1, DonemTuru.YAZ


def secilebilir_donemler(tarih=None):
    """Öğrencinin ders seçebileceği dönemler: [(yıl, dönem, deneme durumu), ...].

    İçinde bulunulan dönemde seçilen ders 'alındı', bir sonraki dönemde 'planlandı' olur.
    Yaz okulu bir sonraki dönem olarak önerilmez.
    """
    yil, tur = donem_tarihten(tarih or timezone.localdate())
    if tur == DonemTuru.GUZ:
        sonraki = (yil, DonemTuru.BAHAR)
    else:
        sonraki = (yil + 1, DonemTuru.GUZ)
    return [(yil, tur, DenemeDurumu.ALINDI), (*sonraki, DenemeDurumu.PLANLANDI)]


def _ogrenci_kaydi(kullanici):
    if kullanici is None or kullanici.rol != Rol.OGRENCI:
        raise PermissionDenied('Bu işlemi yalnızca öğrenci yapabilir.')
    try:
        return kullanici.ogrenci
    except Ogrenci.DoesNotExist:
        raise PermissionDenied('Bu hesaba bağlı öğrenci kaydı yok.')


@transaction.atomic
def ders_sec(kullanici, kalemler, yil, donem_turu, tarih=None):
    """Öğrenci ders listesindeki dersleri bir dönem için seçer. Her seçim ayrı, onay bekleyen denemedir."""
    ogrenci = _ogrenci_kaydi(kullanici)
    if ogrenci.kayit_durumu != KayitDurumu.AKTIF:
        raise IslemHatasi('Kaydı aktif olmayan öğrenci ders seçemez.')
    if not kalemler:
        raise IslemHatasi('En az bir ders seçmelisiniz.')
    durumlar = {(y, t): d for y, t, d in secilebilir_donemler(tarih)}
    if (yil, donem_turu) not in durumlar:
        raise IslemHatasi('Bu dönem için ders seçimi yapılamaz.')

    donem, yeni = AkademikDonem.objects.get_or_create(baslangic_yili=yil, donem=donem_turu)
    if yeni:
        islem_kaydet(kullanici, 'donem_ekle', donem, yeni=_deger(donem, ['baslangic_yili', 'donem']))

    denemeler = []
    for kalem in kalemler:
        if kalem.ogrenci_id != ogrenci.pk:
            raise PermissionDenied
        if not kalem.ders.aktif:
            raise IslemHatasi(f'{kalem.ders.kod}: ders katalogda pasif, seçilemez.')
        try:
            denemeler.append(deneme_ekle(kullanici, kalem, donem, durumlar[(yil, donem_turu)]))
        except IslemHatasi as hata:
            raise IslemHatasi(f'{kalem.ders.kod}: {hata}')
    return denemeler


TALEP_ALANLARI = ['ders', 'istenen_ders', 'aciklama', 'durum']


@transaction.atomic
def talep_gonder(kullanici, aciklama, ders=None, istenen_ders=''):
    """Ders listesinde olmayan ders için talep. Ya katalogdan ders seçilir ya da ders adı yazılır."""
    ogrenci = _ogrenci_kaydi(kullanici)
    istenen_ders = (istenen_ders or '').strip()
    aciklama = (aciklama or '').strip()
    if bool(ders) == bool(istenen_ders):
        raise IslemHatasi('Katalogdan bir ders seçin ya da katalogda olmayan dersin adını yazın (ikisinden biri).')
    if not aciklama:
        raise IslemHatasi('Talebin nedenini açıklamanız zorunludur.')
    if ders:
        if not ders.aktif:
            raise IslemHatasi('Pasif ders için talep gönderilemez.')
        if ders.tur != DersTuru.SECMELI_HAVUZ and \
                ogrenci.ders_listesi.filter(ders=ders, listede=True).exists():
            raise IslemHatasi(f'{ders.kod} zaten ders listenizde.')
        if ogrenci.ders_talepleri.filter(ders=ders, durum=TalepDurumu.BEKLIYOR).exists():
            raise IslemHatasi(f'{ders.kod} için bekleyen bir talebiniz zaten var.')
    talep = DersTalebi.objects.create(
        ogrenci=ogrenci, ders=ders, istenen_ders=istenen_ders, aciklama=aciklama,
    )
    islem_kaydet(kullanici, 'talep_gonder', talep, yeni=_deger(talep, TALEP_ALANLARI))
    return talep


def _talep_bekliyor_olmali(talep):
    if talep.durum != TalepDurumu.BEKLIYOR:
        raise IslemHatasi('Bu talep zaten yanıtlanmış.')


@transaction.atomic
def talep_kabul(kullanici, talep, ders, yanit=''):
    """Talebi kabul eder ve dersi öğrencinin listesine ekler.

    Talep katalogda olmayan bir ders içinse koordinatör önce dersi kataloğa ekler, sonra burada seçer.
    """
    _koordinator_olmali(kullanici)
    _talep_bekliyor_olmali(talep)
    if ders is None:
        raise IslemHatasi('Listeye eklenecek dersi katalogdan seçin.')
    kalem = listeye_ders_ekle(
        kullanici, talep.ogrenci, ders, gerekce=f'Öğrenci talebi #{talep.pk}: {talep.aciklama}',
    )
    eski = _deger(talep, ['durum'])
    talep.durum = TalepDurumu.KABUL
    talep.yanit = (yanit or '').strip()
    talep.yanitlayan = kullanici
    talep.yanit_tarihi = timezone.now()
    talep.eklenen_kalem = kalem
    talep.save()
    islem_kaydet(kullanici, 'talep_kabul', talep, eski=eski,
                 yeni={**_deger(talep, ['durum']), 'eklenen_ders': ders.kod}, aciklama=talep.yanit)
    return talep


@transaction.atomic
def talep_reddet(kullanici, talep, gerekce):
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    _talep_bekliyor_olmali(talep)
    eski = _deger(talep, ['durum'])
    talep.durum = TalepDurumu.RED
    talep.yanit = gerekce.strip()
    talep.yanitlayan = kullanici
    talep.yanit_tarihi = timezone.now()
    talep.save()
    islem_kaydet(kullanici, 'talep_reddet', talep, eski=eski,
                 yeni=_deger(talep, ['durum']), aciklama=talep.yanit)
    return talep


# ---------------------------------------------------------------------------
# Belgeler
# ---------------------------------------------------------------------------

def belge_deposu():
    """Belgelerin saklandığı yer: web kökü dışında, MEDIA_URL'siz (doğrudan adresle açılamaz)."""
    return FileSystemStorage(location=settings.KORUMALI_DOSYA_KOKU)


def dosya_kontrol(dosya):
    """Boyut ve içerik kontrolü. Tür, uzantıya değil dosyanın ilk baytlarına bakılarak belirlenir.

    Dönüş: dosyanın MIME türü (ör. 'application/pdf').
    """
    azami = settings.BELGE_AZAMI_BOYUT
    if dosya.size == 0:
        raise IslemHatasi('Dosya boş.')
    if dosya.size > azami:
        raise IslemHatasi(f'Dosya en fazla {azami // (1024 * 1024)} MB olabilir.')
    dosya.seek(0)
    mime = magic.from_buffer(dosya.read(2048), mime=True)
    dosya.seek(0)
    if mime not in settings.BELGE_IZINLI_TURLER:
        raise IslemHatasi('Yalnızca PDF, JPG veya PNG dosyası yüklenebilir.')
    uzanti = Path(dosya.name).suffix.lower()
    beklenen = {settings.BELGE_IZINLI_TURLER[mime]} | ({'.jpeg'} if mime == 'image/jpeg' else set())
    if uzanti not in beklenen:
        raise IslemHatasi('Dosya uzantısı, dosyanın içeriğiyle uyuşmuyor.')
    return mime


def belge_donemleri(ogrenci, tarih=None):
    """Belge yüklerken seçilebilecek dönemler: kabul döneminden bir sonraki döneme kadar."""
    son = secilebilir_donemler(tarih)[-1]
    son_sira = (son[0], [DonemTuru.GUZ, DonemTuru.BAHAR, DonemTuru.YAZ].index(son[1]))
    idler = [d.pk for d in AkademikDonem.objects.all() if ogrenci.kabul_donemi.sira <= d.sira <= son_sira]
    return AkademikDonem.objects.filter(pk__in=idler)


BELGE_ALANLARI = ['tur', 'donem', 'surum', 'orijinal_ad', 'mime_turu', 'boyut', 'sha256', 'durum']


class _SaklananDosya:
    """Kontrol edilip diske yazılmış dosya. Kayıt oluşturulamazsa geri_al() ile silinir."""

    def __init__(self, dosya, klasor):
        self.mime = dosya_kontrol(dosya)
        ozet = hashlib.sha256()
        for parca in dosya.chunks():
            ozet.update(parca)
        dosya.seek(0)
        self.sha256 = ozet.hexdigest()
        self.boyut = dosya.size
        self.ad = Path(dosya.name).name[:200]
        self.depo = belge_deposu()
        # Öğrencinin verdiği dosya adı diskte kullanılmaz (yol enjeksiyonu, ad çakışması).
        self.yol = self.depo.save(f'{klasor}/{uuid.uuid4().hex}{settings.BELGE_IZINLI_TURLER[self.mime]}', dosya)

    def geri_al(self):
        self.depo.delete(self.yol)


@transaction.atomic
def belge_yukle(kullanici, tur, dosya, donem=None, aciklama='', *, ogrenci=None, istek=None):
    """Belge yükler. Aynı tür ve dönemde önceki belge varsa yeni sürüm olur; eskisi kalır.

    - Öğrenci yalnızca kendi kartına yükler (ogrenci parametresi yok sayılır), resmî yazı yükleyemez.
      `istek` verilirse koordinatörün ek belge isteğine yanıttır: tür ve dönem istekten gelir.
    - Koordinatör `ogrenci` vererek her türlü belgeyi yükler; kendi yüklediği belge doğrudan onaylıdır.
    """
    if kullanici is not None and kullanici.rol == Rol.KOORDINATOR:
        if ogrenci is None:
            raise IslemHatasi('Belgenin yükleneceği öğrenci seçilmelidir.')
        if istek is not None:
            raise IslemHatasi('Ek belge isteğine yalnızca öğrenci yanıt verir.')
    else:
        ogrenci = _ogrenci_kaydi(kullanici)
        if tur == BelgeTuru.RESMI_YAZI:
            raise IslemHatasi('Resmî yazıları yalnızca koordinatör yükleyebilir.')
        if istek is not None:
            if istek.ogrenci_id != ogrenci.pk:
                raise PermissionDenied
            if not istek.acik:
                raise IslemHatasi('Bu isteğe zaten belge yüklendi.')
            tur, donem = istek.tur, istek.donem
    if tur not in BelgeTuru.values:
        raise IslemHatasi('Geçersiz belge türü.')
    if tur in DONEMLI_BELGE_TURLERI and donem is None:
        raise IslemHatasi(f'{BelgeTuru(tur).label} için dönem seçilmesi zorunludur.')

    onceki = ogrenci.belgeler.filter(tur=tur, donem=donem).order_by('-surum').first()
    if onceki and onceki.durum == BelgeDurumu.BEKLIYOR:
        raise IslemHatasi('Bu belgenin önceki sürümü hâlâ onay bekliyor. '
                          'Koordinatör yanıtladıktan sonra yeni sürüm yükleyebilirsiniz.')

    saklanan = _SaklananDosya(dosya, f'belgeler/{ogrenci.ogrenci_no}')
    try:
        koordinator = kullanici.rol == Rol.KOORDINATOR
        belge = Belge.objects.create(
            ogrenci=ogrenci, tur=tur, donem=donem, surum=(onceki.surum + 1) if onceki else 1,
            aciklama=(aciklama or '').strip(), dosya_yolu=saklanan.yol, orijinal_ad=saklanan.ad,
            mime_turu=saklanan.mime, boyut=saklanan.boyut, sha256=saklanan.sha256, yukleyen=kullanici,
            durum=BelgeDurumu.ONAYLANDI if koordinator else BelgeDurumu.BEKLIYOR,
            inceleyen=kullanici if koordinator else None,
            inceleme_tarihi=timezone.now() if koordinator else None,
        )
        islem_kaydet(kullanici, 'belge_yukle', belge, yeni=_deger(belge, BELGE_ALANLARI))
        if istek is not None:
            eski = {'belge': str(istek.belge_id) if istek.belge_id else None}
            istek.belge = belge
            istek.save()
            islem_kaydet(kullanici, 'belge_istegi_yanit', istek, eski=eski, yeni={'belge': str(belge.pk)})
    except Exception:
        saklanan.geri_al()  # kayıt oluşmadıysa diskte sahipsiz dosya kalmasın
        raise
    return belge


# ---------------------------------------------------------------------------
# Ek belge isteği ve mesajlaşma
# ---------------------------------------------------------------------------

MESAJ_AZAMI_UZUNLUK = 5000


@transaction.atomic
def belge_iste(kullanici, ogrenci, tur, aciklama, donem=None):
    """Koordinatör öğrenciden ek belge ister. İstek yazışmaya da mesaj olarak düşer."""
    _koordinator_olmali(kullanici)
    _gerekce_olmali(aciklama)
    if tur not in dict(OGRENCI_BELGE_TURLERI):
        raise IslemHatasi('Bu belge türü öğrenciden istenemez.')
    if tur in DONEMLI_BELGE_TURLERI and donem is None:
        raise IslemHatasi(f'{BelgeTuru(tur).label} için dönem seçilmesi zorunludur.')
    istek = BelgeIstegi.objects.create(
        ogrenci=ogrenci, tur=tur, donem=donem, aciklama=aciklama.strip(), isteyen=kullanici,
    )
    islem_kaydet(kullanici, 'belge_iste', istek, yeni=_deger(istek, ['tur', 'donem', 'aciklama']))
    donem_metni = f' ({donem})' if donem else ''
    _mesaj_olustur(kullanici, ogrenci, f'Ek belge istendi: {BelgeTuru(tur).label}{donem_metni}.\n{istek.aciklama}',
                   istek=istek)
    return istek


def _mesaj_olustur(kullanici, ogrenci, metin, dosya=None, istek=None):
    metin = (metin or '').strip()
    if not metin:
        raise IslemHatasi('Mesaj boş olamaz.')
    if len(metin) > MESAJ_AZAMI_UZUNLUK:
        raise IslemHatasi(f'Mesaj en fazla {MESAJ_AZAMI_UZUNLUK} karakter olabilir.')
    saklanan = _SaklananDosya(dosya, f'mesajlar/{ogrenci.ogrenci_no}') if dosya else None
    try:
        mesaj = Mesaj.objects.create(
            ogrenci=ogrenci, gonderen=kullanici, metin=metin, istek=istek,
            **({'ek_yolu': saklanan.yol, 'ek_adi': saklanan.ad, 'ek_mime': saklanan.mime,
                'ek_boyut': saklanan.boyut, 'ek_sha256': saklanan.sha256} if saklanan else {}),
        )
        islem_kaydet(kullanici, 'mesaj_gonder', mesaj,
                     yeni={'metin': metin[:300], 'ek': saklanan.ad if saklanan else None})
    except Exception:
        if saklanan:
            saklanan.geri_al()
        raise
    return mesaj


@transaction.atomic
def mesaj_gonder(kullanici, metin, dosya=None, *, ogrenci=None):
    """Koordinatör `ogrenci`nin yazışmasına yazar; öğrenci yalnızca kendi yazışmasına yazar."""
    if kullanici is not None and kullanici.rol == Rol.KOORDINATOR:
        if ogrenci is None:
            raise IslemHatasi('Mesajın gönderileceği öğrenci seçilmelidir.')
    else:
        ogrenci = _ogrenci_kaydi(kullanici)
    return _mesaj_olustur(kullanici, ogrenci, metin, dosya)


def _okunmamislar(kullanici, ogrenci=None):
    """Kullanıcının karşı taraftan gelen, okumadığı mesajlar. Bölüm başkanı yazışmanın tarafı değildir."""
    mesajlar = Mesaj.objects.filter(okunma_tarihi__isnull=True)
    if kullanici.rol == Rol.KOORDINATOR:
        mesajlar = mesajlar.filter(gonderen__rol=Rol.OGRENCI)
    elif kullanici.rol == Rol.OGRENCI:
        mesajlar = mesajlar.filter(ogrenci__kullanici=kullanici).exclude(gonderen=kullanici)
    else:
        return Mesaj.objects.none()
    return mesajlar.filter(ogrenci=ogrenci) if ogrenci is not None else mesajlar


def okunmamis_mesaj_sayisi(kullanici):
    return _okunmamislar(kullanici).count()


def mesajlari_okundu_isaretle(kullanici, ogrenci):
    """Yazışmayı açan taraf için karşı taraftan gelen mesajlar okundu olur (bildirim kalkar)."""
    for mesaj in _okunmamislar(kullanici, ogrenci):
        mesaj.okunma_tarihi = timezone.now()
        mesaj.save(update_fields=['okunma_tarihi', 'guncellenme'])


def _belge_bekliyor_olmali(belge):
    if belge.durum != BelgeDurumu.BEKLIYOR:
        raise IslemHatasi('Yalnızca onay bekleyen belge incelenebilir.')


@transaction.atomic
def belge_onayla(kullanici, belge):
    _koordinator_olmali(kullanici)
    _belge_bekliyor_olmali(belge)
    eski = _deger(belge, ['durum'])
    belge.durum = BelgeDurumu.ONAYLANDI
    belge.inceleyen = kullanici
    belge.inceleme_tarihi = timezone.now()
    belge.save()
    islem_kaydet(kullanici, 'belge_onayla', belge, eski=eski, yeni=_deger(belge, ['durum']))
    return belge


@transaction.atomic
def belge_reddet(kullanici, belge, gerekce):
    """Ret gerekçesi öğrenciye gösterilir (ör. 'imza eksik, yeniden yükleyin')."""
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    _belge_bekliyor_olmali(belge)
    eski = _deger(belge, ['durum'])
    belge.durum = BelgeDurumu.REDDEDILDI
    belge.red_gerekcesi = gerekce.strip()
    belge.inceleyen = kullanici
    belge.inceleme_tarihi = timezone.now()
    belge.save()
    islem_kaydet(kullanici, 'belge_reddet', belge, eski=eski,
                 yeni=_deger(belge, ['durum']), aciklama=belge.red_gerekcesi)
    return belge


# ---------------------------------------------------------------------------
# Dönem sonu not girişi
# ---------------------------------------------------------------------------

NOT_ALANLARI = ['harf_notu', 'durum', 'transkript_id', 'onay_durumu']


def _donem_sirasi(yil, tur):
    return yil, [DonemTuru.GUZ, DonemTuru.BAHAR, DonemTuru.YAZ].index(tur)


def not_girilebilir_denemeler(ogrenci, tarih=None):
    """Öğrencinin not girebileceği kayıtlar: koordinatörün onayladığı 'alındı' denemeleri,
    içinde bulunulan veya geçmiş bir dönemde, listede olan, onay bekleyen not girişi olmayan."""
    simdi = _donem_sirasi(*donem_tarihten(tarih or timezone.localdate()))
    denemeler = (
        DersDenemesi.objects
        .filter(liste_kalemi__ogrenci=ogrenci, liste_kalemi__listede=True,
                onay_durumu=OnayDurumu.ONAYLANDI, durum=DenemeDurumu.ALINDI)
        .exclude(not_girisleri__onay_durumu=OnayDurumu.BEKLIYOR)
        .select_related('donem', 'liste_kalemi__ders')
        .prefetch_related('not_girisleri')
        .order_by('donem__baslangic_yili', 'donem__donem', 'liste_kalemi__ders__kod')
    )
    return [d for d in denemeler if d.donem.sira <= simdi]


def donem_transkripti(ogrenci, donem):
    """Dönemin geçerli ÇAP/YDP not belgesi: en son sürüm, reddedilmemişse. Yoksa None.

    Hoca: 'yüklenmeden notlar onaya gönderilemez' — onaylanmış olması gerekmez,
    koordinatör notlarla birlikte inceler.
    """
    son = ogrenci.belgeler.filter(tur=BelgeTuru.TRANSKRIPT, donem=donem).order_by('-surum').first()
    return son if son and son.durum != BelgeDurumu.REDDEDILDI else None


@transaction.atomic
def not_gir(kullanici, girisler, tarih=None):
    """Öğrenci dönem sonu notlarını onaya gönderir. girisler: [(deneme, harf_notu, durum), ...].

    Her dönemin ÇAP/YDP not belgesi (transkript) yüklenmiş olmalıdır.
    """
    ogrenci = _ogrenci_kaydi(kullanici)
    if not girisler:
        raise IslemHatasi('En az bir dersin notunu girmelisiniz.')
    uygun = {d.pk for d in not_girilebilir_denemeler(ogrenci, tarih)}
    kayitlar = []
    for deneme, harf_notu, durum in girisler:
        if deneme.liste_kalemi.ogrenci_id != ogrenci.pk:
            raise PermissionDenied
        kod = deneme.liste_kalemi.ders.kod
        if deneme.pk not in uygun:
            raise IslemHatasi(f'{kod}: bu kayda not girilemez (onaylı “alındı” kaydı değil '
                              f'veya notu zaten onay bekliyor).')
        if harf_notu not in HarfNotu.values or durum not in (DenemeDurumu.GECTI, DenemeDurumu.KALDI):
            raise IslemHatasi(f'{kod}: harf notu ve Geçti/Kaldı durumu seçilmelidir.')
        transkript = donem_transkripti(ogrenci, deneme.donem)
        if transkript is None:
            raise IslemHatasi(f'{deneme.donem} dönemi için ÇAP/YDP not belgesi (transkript) yüklenmeden '
                              f'notlar onaya gönderilemez.')
        giris = NotGirisi.objects.create(
            deneme=deneme, harf_notu=harf_notu, durum=durum, transkript=transkript, giren=kullanici,
        )
        islem_kaydet(kullanici, 'not_gir', giris, yeni=_deger(giris, NOT_ALANLARI))
        kayitlar.append(giris)
    return kayitlar


def _not_bekliyor_olmali(giris):
    if giris.onay_durumu != OnayDurumu.BEKLIYOR:
        raise IslemHatasi('Yalnızca onay bekleyen not girişi incelenebilir.')


@transaction.atomic
def not_onayla(kullanici, giris):
    """Not onaylanınca deneme Geçti/Kaldı olur ve hesaplara girer. Deneme yine kilitli kalır."""
    _koordinator_olmali(kullanici)
    _not_bekliyor_olmali(giris)
    deneme = giris.deneme
    if deneme.onay_durumu != OnayDurumu.ONAYLANDI or deneme.durum != DenemeDurumu.ALINDI:
        raise IslemHatasi('Ders kaydı bu arada değişmiş (iptal veya düzeltme); not onaylanamaz. Reddedin.')

    eski_deneme = _deger(deneme, DENEME_ALANLARI)
    deneme.durum, deneme.harf_notu = giris.durum, giris.harf_notu
    deneme._kilit_acik = True
    deneme.save()

    giris.onay_durumu = OnayDurumu.ONAYLANDI
    giris.inceleyen = kullanici
    giris.inceleme_tarihi = timezone.now()
    giris.save()
    islem_kaydet(kullanici, 'not_onayla', giris, eski={'onay_durumu': OnayDurumu.BEKLIYOR},
                 yeni={'onay_durumu': OnayDurumu.ONAYLANDI})
    islem_kaydet(kullanici, 'deneme_not_isle', deneme, eski=eski_deneme, yeni=_deger(deneme, DENEME_ALANLARI),
                 aciklama=f'Not girişi #{giris.pk} onaylandı')
    return giris


@transaction.atomic
def not_reddet(kullanici, giris, gerekce):
    _koordinator_olmali(kullanici)
    _gerekce_olmali(gerekce)
    _not_bekliyor_olmali(giris)
    giris.onay_durumu = OnayDurumu.REDDEDILDI
    giris.red_gerekcesi = gerekce.strip()
    giris.inceleyen = kullanici
    giris.inceleme_tarihi = timezone.now()
    giris.save()
    islem_kaydet(kullanici, 'not_reddet', giris, eski={'onay_durumu': OnayDurumu.BEKLIYOR},
                 yeni={'onay_durumu': OnayDurumu.REDDEDILDI}, aciklama=giris.red_gerekcesi)
    return giris


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
