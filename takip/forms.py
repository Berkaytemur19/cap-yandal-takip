from django import forms
from django.core.validators import RegexValidator

from .models import (
    AkademikDonem, DenemeDurumu, Ders, DersDenemesi, DersTuru, DonemTuru, OgrenciDers, OnayDurumu,
    ProgramTuru, Protokol,
)


class BootstrapMixin:
    """Alanlara Bootstrap 5 sınıflarını ekler."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for alan in self.fields.values():
            sinif = 'form-select' if isinstance(alan.widget, forms.Select) else 'form-control'
            alan.widget.attrs.setdefault('class', sinif)


class OgrenciEkleForm(BootstrapMixin, forms.Form):
    ogrenci_no = forms.CharField(
        label='Öğrenci no', max_length=20,
        validators=[RegexValidator(r'^\d{5,20}$', 'Öğrenci no yalnızca rakamlardan oluşmalı (en az 5).')],
    )
    ad = forms.CharField(max_length=100)
    soyad = forms.CharField(max_length=100)
    okul_eposta = forms.EmailField(label='Okul e-postası')
    program_turu = forms.ChoiceField(label='Program', choices=ProgramTuru.choices)
    ana_dal_bolumu = forms.CharField(label='Ana dal bölümü', max_length=200)
    protokol = forms.ModelChoiceField(queryset=Protokol.objects.filter(aktif=True))
    kabul_yili = forms.IntegerField(
        label='Kabul yılı', min_value=2000, max_value=2100, help_text='2025-2026 için 2025',
    )
    kabul_donemi = forms.ChoiceField(label='Kabul dönemi', choices=DonemTuru.choices)

    def clean(self):
        veri = super().clean()
        protokol, program = veri.get('protokol'), veri.get('program_turu')
        if protokol and program and protokol.program_turu != program:
            self.add_error('protokol', 'Protokol, seçilen programla (ÇAP/YDP) uyuşmuyor.')
        return veri


class DersForm(BootstrapMixin, forms.Form):
    kod = forms.CharField(max_length=20)
    ad = forms.CharField(max_length=200)
    akts = forms.IntegerField(label='AKTS', min_value=1, max_value=60)
    tur = forms.ChoiceField(label='Tür', choices=DersTuru.choices)

    def __init__(self, *args, kod_degistirilemez=False, **kwargs):
        super().__init__(*args, **kwargs)
        if kod_degistirilemez:
            self.fields['kod'].disabled = True
            self.fields['kod'].help_text = 'Ders kodu benzersiz anahtardır, değiştirilemez.'


class DersSecForm(forms.Form):
    """Öğrencinin kendi ders listesinden bir dönem için ders seçmesi.

    Seçenekler yalnızca öğrencinin kendi listesindeki, tamamlanmamış ve katalogda aktif derslerdir;
    başka öğrencinin kalem numarası gönderilirse form geçersiz olur.
    """

    donem = forms.ChoiceField(label='Dönem', widget=forms.RadioSelect)
    kalemler = forms.ModelMultipleChoiceField(
        label='Dersler', queryset=OgrenciDers.objects.none(), widget=forms.CheckboxSelectMultiple,
        error_messages={'required': 'En az bir ders seçmelisiniz.'},
    )

    def __init__(self, *args, ogrenci, donemler, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['donem'].choices = [
            (f'{yil}-{tur}', f'{AkademikDonem(baslangic_yili=yil, donem=tur)} — {DenemeDurumu(durum).label.lower()}')
            for yil, tur, durum in donemler
        ]
        self.fields['donem'].initial = self.fields['donem'].choices[0][0]
        tamamlanan = DersDenemesi.objects.filter(
            liste_kalemi__ogrenci=ogrenci, onay_durumu=OnayDurumu.ONAYLANDI,
            durum__in=[DenemeDurumu.GECTI, DenemeDurumu.MUAF],
        ).values('liste_kalemi')
        self.fields['kalemler'].queryset = (
            ogrenci.ders_listesi.filter(listede=True, ders__aktif=True)
            .exclude(pk__in=tamamlanan)
            .select_related('ders')
            .prefetch_related('denemeler__donem')
            .order_by('yariyil', 'ders__kod')
        )

    def secilen_donem(self):
        yil, tur = self.cleaned_data['donem'].split('-')
        return int(yil), tur


class TalepForm(BootstrapMixin, forms.Form):
    ders = forms.ModelChoiceField(
        label='Katalogdaki ders', queryset=Ders.objects.none(), required=False,
        empty_label='— Katalogda yoksa boş bırakın —',
    )
    istenen_ders = forms.CharField(
        label='Katalogda olmayan ders', max_length=200, required=False,
        help_text='Dersin kodu ve adı, örn: 3301999 Bulut Bilişim',
    )
    aciklama = forms.CharField(
        label='Açıklama', widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Bu dersi neden almak istediğinizi kısaca yazın.',
    )

    def __init__(self, *args, ogrenci, **kwargs):
        super().__init__(*args, **kwargs)
        listedeki = ogrenci.ders_listesi.filter(listede=True).exclude(
            ders__tur=DersTuru.SECMELI_HAVUZ).values('ders')
        self.fields['ders'].queryset = Ders.objects.filter(aktif=True).exclude(pk__in=listedeki)

    def clean(self):
        veri = super().clean()
        if bool(veri.get('ders')) == bool((veri.get('istenen_ders') or '').strip()):
            raise forms.ValidationError(
                'Katalogdan bir ders seçin ya da katalogda olmayan dersin adını yazın (ikisinden biri).'
            )
        return veri
