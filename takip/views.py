"""Ekranlar. Her view @rol_gerekli ile sunucu tarafında korunur.

Veriyi değiştiren view'lar işi services modülüne bırakır; burada doğrudan .save() yapılmaz.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from hesaplar.models import Rol
from hesaplar.yetki import rol_gerekli

from . import services
from .forms import DersForm, OgrenciEkleForm
from .models import Ders, DersDenemesi, IslemKaydi, Ogrenci, OnayDurumu, ProgramTuru

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
    return render(request, 'takip/ogrenci_detay.html', _ders_listesi_baglami(ogrenci))


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
