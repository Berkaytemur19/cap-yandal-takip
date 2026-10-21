"""Ekranlar. Her view @rol_gerekli ile sunucu tarafında korunur.

Veriyi değiştiren view'lar işi services modülüne bırakır; burada doğrudan .save() yapılmaz.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from hesaplar.models import Rol
from hesaplar.yetki import rol_gerekli

from . import services
from .forms import BelgeYukleForm, DersForm, DersSecForm, OgrenciEkleForm, TalepForm
from .models import (
    Belge, BelgeDurumu, Ders, DersDenemesi, DersTalebi, IslemKaydi, Ogrenci, OnayDurumu, ProgramTuru,
    TalepDurumu,
)

KOORD = Rol.KOORDINATOR
BASKAN = Rol.BOLUM_BASKANI
OGRENCI = Rol.OGRENCI


# ---------------------------------------------------------------------------
# Ana sayfa
# ---------------------------------------------------------------------------

@login_required
def ana_sayfa(request):
    """Role göre ana sayfa. Öğrenci kendi sayfasına yönlendirilir."""
    if request.user.ogrenci_mi:
        return redirect('benim')
    if request.user.rol not in (KOORD, BASKAN):
        # Rolü olmayan hesap (ör. rol seçilmeden açılmış süper kullanıcı) hiçbir şey göremez.
        return render(request, 'takip/rol_yok.html', status=403)

    sayilar = Ogrenci.objects.aggregate(
        cap=Count('pk', filter=Q(program_turu=ProgramTuru.CAP, kayit_durumu='AKTIF')),
        ydp=Count('pk', filter=Q(program_turu=ProgramTuru.YDP, kayit_durumu='AKTIF')),
    )
    sayilar['bekleyen'] = DersDenemesi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).count()
    sayilar['aktif_ders'] = Ders.objects.filter(aktif=True).count()
    sayilar['talep'] = DersTalebi.objects.filter(durum=TalepDurumu.BEKLIYOR).count()
    sayilar['belge'] = Belge.objects.filter(durum=BelgeDurumu.BEKLIYOR).count()
    son_islemler = IslemKaydi.objects.select_related('kullanici')[:8]
    return render(request, 'takip/ana_sayfa.html', {'sayilar': sayilar, 'son_islemler': son_islemler})


# ---------------------------------------------------------------------------
# Öğrenci listesi ve detay (koordinatör + bölüm başkanı)
# ---------------------------------------------------------------------------

@rol_gerekli(KOORD, BASKAN)
def ogrenci_listesi(request):
    ogrenciler = Ogrenci.objects.select_related('kabul_donemi', 'protokol')
    program = request.GET.get('program', '')
    if program in ProgramTuru.values:
        ogrenciler = ogrenciler.filter(program_turu=program)
    q = request.GET.get('q', '').strip()
    if q:
        ogrenciler = ogrenciler.filter(
            Q(ogrenci_no__icontains=q) | Q(ad__icontains=q) | Q(soyad__icontains=q)
        )
    return render(request, 'takip/ogrenci_listesi.html', {
        'ogrenciler': ogrenciler, 'program': program, 'q': q, 'programlar': ProgramTuru.choices,
    })


def _ders_listesi_baglami(ogrenci):
    kalemler = list(
        ogrenci.ders_listesi.select_related('ders', 'cikaran')
        .prefetch_related('denemeler__donem')
        .order_by('yariyil', 'ders__kod')
    )
    return {
        'ogrenci': ogrenci,
        'kalemler': [k for k in kalemler if k.listede],
        'cikarilanlar': [k for k in kalemler if not k.listede],
        'ozet': ogrenci.ders_ozeti(),
        'gano_kayitlari': ogrenci.gano_kayitlari.filter(iptal=False).select_related('donem'),
    }


@rol_gerekli(KOORD, BASKAN)
def ogrenci_detay(request, pk):
    ogrenci = get_object_or_404(Ogrenci.objects.select_related('kabul_donemi', 'protokol'), pk=pk)
    baglam = _ders_listesi_baglami(ogrenci)
    baglam['belgeler'] = ogrenci.belgeler.select_related('donem')
    return render(request, 'takip/ogrenci_detay.html', baglam)


@rol_gerekli(KOORD)
def ogrenci_ekle(request):
    form = OgrenciEkleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        v = form.cleaned_data
        try:
            donem = services.donem_bul_veya_ekle(request.user, v['kabul_yili'], v['kabul_donemi'])
            ogrenci, sifre = services.ogrenci_ekle(
                request.user,
                ogrenci_no=v['ogrenci_no'], ad=v['ad'], soyad=v['soyad'], okul_eposta=v['okul_eposta'],
                program_turu=v['program_turu'], ana_dal_bolumu=v['ana_dal_bolumu'],
                protokol=v['protokol'], kabul_donemi=donem,
            )
        except services.IslemHatasi as hata:
            form.add_error(None, str(hata))
        else:
            # Geçici şifre yalnızca bu sayfada bir kez gösterilir; oturuma/mesaja yazılmaz.
            return render(request, 'takip/ogrenci_eklendi.html', {'ogrenci': ogrenci, 'sifre': sifre})
    return render(request, 'takip/ogrenci_ekle.html', {'form': form})


# ---------------------------------------------------------------------------
# Öğrencinin kendi sayfası
# ---------------------------------------------------------------------------

@rol_gerekli(OGRENCI)
def benim(request):
    """URL'de öğrenci numarası yok: öğrenci yalnızca oturumdaki kendi kaydını görür."""
    try:
        ogrenci = request.user.ogrenci
    except Ogrenci.DoesNotExist:
        raise Http404('Bu hesaba bağlı öğrenci kaydı yok.')
    baglam = _ders_listesi_baglami(ogrenci)
    baglam.pop('gano_kayitlari')  # GANO kaynak notları koordinatöre aittir
    return render(request, 'takip/benim.html', baglam)


# ---------------------------------------------------------------------------
# Ders kataloğu (koordinatör)
# ---------------------------------------------------------------------------

@rol_gerekli(KOORD)
def ders_katalogu(request):
    form = DersForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        v = form.cleaned_data
        try:
            ders = services.katalog_dersi_ekle(request.user, v['kod'], v['ad'], v['akts'], v['tur'])
        except services.IslemHatasi as hata:
            form.add_error('kod', str(hata))
        else:
            messages.success(request, f'{ders} kataloğa eklendi.')
            return redirect('ders_katalogu')
    dersler = Ders.objects.all().order_by('-aktif', 'kod')
    return render(request, 'takip/ders_katalogu.html', {'form': form, 'dersler': dersler})


@rol_gerekli(KOORD)
def ders_duzenle(request, pk):
    ders = get_object_or_404(Ders, pk=pk)
    baslangic = {'kod': ders.kod, 'ad': ders.ad, 'akts': ders.akts, 'tur': ders.tur}
    form = DersForm(request.POST or None, initial=baslangic, kod_degistirilemez=True)
    if request.method == 'POST' and form.is_valid():
        v = form.cleaned_data
        services.katalog_dersi_guncelle(request.user, ders, v['ad'], v['akts'], v['tur'])
        messages.success(request, f'{ders} güncellendi.')
        return redirect('ders_katalogu')
    return render(request, 'takip/ders_duzenle.html', {'form': form, 'ders': ders})


@require_POST
@rol_gerekli(KOORD)
def ders_aktiflik(request, pk):
    ders = get_object_or_404(Ders, pk=pk)
    aktif = request.POST.get('aktif') == '1'
    services.katalog_dersi_aktiflik(request.user, ders, aktif)
    messages.success(request, f'{ders} {"aktifleştirildi" if aktif else "pasife alındı"}.')
    return redirect('ders_katalogu')


# ---------------------------------------------------------------------------
# İşlem geçmişi (koordinatör + bölüm başkanı)
# ---------------------------------------------------------------------------

@rol_gerekli(KOORD, BASKAN)
def islem_gecmisi(request):
    kayitlar = IslemKaydi.objects.select_related('kullanici')
    sayfa = Paginator(kayitlar, 50).get_page(request.GET.get('sayfa'))
    return render(request, 'takip/islem_gecmisi.html', {'sayfa': sayfa})


# ---------------------------------------------------------------------------
# Onay bekleyen ders kayıtları (koordinatör)
# ---------------------------------------------------------------------------

@rol_gerekli(KOORD)
def onay_bekleyenler(request):
    """Öğrencilerin girdiği, onay bekleyen ders denemeleri. En eski kayıt en üstte."""
    denemeler = (
        DersDenemesi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR)
        .select_related('liste_kalemi__ogrenci', 'liste_kalemi__ders', 'donem', 'giren')
        .order_by('olusturulma')
    )
    return render(request, 'takip/onay_bekleyenler.html', {'denemeler': denemeler})


@require_POST
@rol_gerekli(KOORD)
def deneme_onayla(request, pk):
    deneme = get_object_or_404(DersDenemesi, pk=pk)
    try:
        services.deneme_onayla(request.user, deneme)
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'{deneme.liste_kalemi} ({deneme.donem}) onaylandı.')
    return redirect('onay_bekleyenler')


@require_POST
@rol_gerekli(KOORD)
def deneme_reddet(request, pk):
    deneme = get_object_or_404(DersDenemesi, pk=pk)
    try:
        services.deneme_reddet(request.user, deneme, request.POST.get('gerekce', '').strip())
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'{deneme.liste_kalemi} ({deneme.donem}) reddedildi.')
    return redirect('onay_bekleyenler')


# ---------------------------------------------------------------------------
# Öğrencinin ders seçimi ve ders talepleri
# ---------------------------------------------------------------------------

@rol_gerekli(OGRENCI)
def ders_sec(request):
    """Öğrenci ders listesinden dönemlik ders seçer; listesinde olmayan ders için talep gönderir.

    Sayfada iki form var; hangisinin gönderildiğini gizli 'islem' alanı belirler.
    """
    try:
        ogrenci = request.user.ogrenci
    except Ogrenci.DoesNotExist:
        raise Http404('Bu hesaba bağlı öğrenci kaydı yok.')

    donemler = services.secilebilir_donemler()
    islem = request.POST.get('islem') if request.method == 'POST' else None
    secim_formu = DersSecForm(request.POST if islem == 'sec' else None, ogrenci=ogrenci, donemler=donemler)
    talep_formu = TalepForm(request.POST if islem == 'talep' else None, ogrenci=ogrenci)

    if islem == 'sec' and secim_formu.is_valid():
        yil, tur = secim_formu.secilen_donem()
        kalemler = list(secim_formu.cleaned_data['kalemler'])
        try:
            services.ders_sec(request.user, kalemler, yil, tur)
        except services.IslemHatasi as hata:
            secim_formu.add_error(None, str(hata))
        else:
            messages.success(request, f'{len(kalemler)} ders seçildi; koordinatör onayı bekleniyor.')
            return redirect('ders_sec')

    if islem == 'talep' and talep_formu.is_valid():
        v = talep_formu.cleaned_data
        try:
            services.talep_gonder(request.user, v['aciklama'], ders=v['ders'], istenen_ders=v['istenen_ders'])
        except services.IslemHatasi as hata:
            talep_formu.add_error(None, str(hata))
        else:
            messages.success(request, 'Ders talebiniz koordinatöre gönderildi.')
            return redirect('ders_sec')

    return render(request, 'takip/ders_sec.html', {
        'ogrenci': ogrenci,
        'secim_formu': secim_formu,
        'talep_formu': talep_formu,
        'talepler': ogrenci.ders_talepleri.select_related('ders', 'eklenen_kalem__ders'),
    })


@rol_gerekli(KOORD)
def talepler(request):
    """Öğrencilerin ders talepleri. Bekleyenler en üstte, en eski önce."""
    tum = DersTalebi.objects.select_related('ogrenci', 'ders', 'yanitlayan')
    return render(request, 'takip/talepler.html', {
        'bekleyenler': tum.filter(durum=TalepDurumu.BEKLIYOR).order_by('olusturulma'),
        'yanitlananlar': tum.exclude(durum=TalepDurumu.BEKLIYOR).order_by('-yanit_tarihi')[:50],
        'dersler': Ders.objects.filter(aktif=True).order_by('kod'),
    })


@require_POST
@rol_gerekli(KOORD)
def talep_kabul(request, pk):
    talep = get_object_or_404(DersTalebi, pk=pk)
    ders = Ders.objects.filter(pk=request.POST.get('ders') or None).first()
    try:
        services.talep_kabul(request.user, talep, ders, request.POST.get('yanit', ''))
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'Talep kabul edildi; {ders.kod} {talep.ogrenci.ad_soyad} listesine eklendi.')
    return redirect('talepler')


@require_POST
@rol_gerekli(KOORD)
def talep_reddet(request, pk):
    talep = get_object_or_404(DersTalebi, pk=pk)
    try:
        services.talep_reddet(request.user, talep, request.POST.get('gerekce', '').strip())
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'{talep.ogrenci.ad_soyad} adlı öğrencinin talebi reddedildi.')
    return redirect('talepler')


# ---------------------------------------------------------------------------
# Belgeler
# ---------------------------------------------------------------------------

@rol_gerekli(OGRENCI)
def belgelerim(request):
    """Öğrenci belge yükler ve kendi belgelerini (tüm sürümleriyle) görür."""
    try:
        ogrenci = request.user.ogrenci
    except Ogrenci.DoesNotExist:
        raise Http404('Bu hesaba bağlı öğrenci kaydı yok.')

    form = BelgeYukleForm(request.POST or None, request.FILES or None,
                          donemler=services.belge_donemleri(ogrenci))
    if request.method == 'POST' and form.is_valid():
        v = form.cleaned_data
        try:
            belge = services.belge_yukle(request.user, v['tur'], v['dosya'], v['donem'], v['aciklama'])
        except services.IslemHatasi as hata:
            form.add_error(None, str(hata))
        else:
            messages.success(request, f'{belge.get_tur_display()} yüklendi; koordinatör onayı bekleniyor.')
            return redirect('belgelerim')

    return render(request, 'takip/belgelerim.html', {
        'form': form, 'belgeler': ogrenci.belgeler.select_related('donem'),
    })


@rol_gerekli(KOORD)
def belgeler(request):
    """Onay bekleyen belgeler (en eski önce) ve son incelenenler."""
    tum = Belge.objects.select_related('ogrenci', 'donem', 'inceleyen')
    return render(request, 'takip/belgeler.html', {
        'bekleyenler': tum.filter(durum=BelgeDurumu.BEKLIYOR).order_by('olusturulma'),
        'incelenenler': tum.exclude(durum=BelgeDurumu.BEKLIYOR).order_by('-inceleme_tarihi')[:50],
    })


@require_POST
@rol_gerekli(KOORD)
def belge_onayla(request, pk):
    belge = get_object_or_404(Belge, pk=pk)
    try:
        services.belge_onayla(request.user, belge)
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'{belge} onaylandı.')
    return redirect('belgeler')


@require_POST
@rol_gerekli(KOORD)
def belge_reddet(request, pk):
    belge = get_object_or_404(Belge, pk=pk)
    try:
        services.belge_reddet(request.user, belge, request.POST.get('gerekce', '').strip())
    except services.IslemHatasi as hata:
        messages.error(request, str(hata))
    else:
        messages.success(request, f'{belge} reddedildi.')
    return redirect('belgeler')


@rol_gerekli(KOORD, BASKAN, OGRENCI)
def belge_dosyasi(request, pk):
    """Belge dosyasını yetki kontrolüyle sunar. Öğrenci yalnızca kendi belgesini açabilir."""
    belge = get_object_or_404(Belge.objects.select_related('ogrenci'), pk=pk)
    if request.user.ogrenci_mi and belge.ogrenci.kullanici_id != request.user.pk:
        raise PermissionDenied
    try:
        dosya = services.belge_deposu().open(belge.dosya_yolu, 'rb')
    except FileNotFoundError:
        raise Http404('Belge dosyası bulunamadı.')
    cevap = FileResponse(dosya, content_type=belge.mime_turu, filename=belge.orijinal_ad)
    cevap['Cache-Control'] = 'private, no-store'
    return cevap
