from django import forms
from django.core.validators import RegexValidator

from .models import DersTuru, DonemTuru, ProgramTuru, Protokol


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
