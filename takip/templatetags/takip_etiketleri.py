from django import template

register = template.Library()

RENKLER = {
    # deneme / kalem durumu
    'GECTI': 'success', 'MUAF': 'info', 'KALDI': 'danger', 'ALINDI': 'primary',
    'PLANLANDI': 'secondary', 'CIKARILDI': 'dark', 'YOK': 'light text-dark',
    # onay durumu
    'BEKLIYOR': 'warning text-dark', 'ONAYLANDI': 'success', 'REDDEDILDI': 'danger', 'IPTAL': 'dark',
    # ders talebi durumu
    'KABUL': 'success', 'RED': 'danger',
    # ek belge isteği durumu
    'YUKLENDI': 'info text-dark',
    # kayıt durumu
    'AKTIF': 'success', 'MEZUN': 'primary', 'SERTIFIKA_ALDI': 'primary', 'KAYDI_SILINDI': 'danger',
}


@register.filter
def rozet(kod):
    """Durum koduna göre Bootstrap rozet rengi döndürür: {{ x.durum|rozet }}"""
    return RENKLER.get(kod, 'secondary')


@register.filter
def esit(a, b):
    """İki değer eşit mi: {% with benim=m.gonderen_id|esit:user.pk %}"""
    return a == b
