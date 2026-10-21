from django.urls import path

from . import views

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('benim/', views.benim, name='benim'),
    path('benim/ders-sec/', views.ders_sec, name='ders_sec'),
    path('ogrenciler/', views.ogrenci_listesi, name='ogrenci_listesi'),
    path('ogrenciler/yeni/', views.ogrenci_ekle, name='ogrenci_ekle'),
    path('ogrenciler/<int:pk>/', views.ogrenci_detay, name='ogrenci_detay'),
    path('dersler/', views.ders_katalogu, name='ders_katalogu'),
    path('dersler/<int:pk>/duzenle/', views.ders_duzenle, name='ders_duzenle'),
    path('dersler/<int:pk>/aktiflik/', views.ders_aktiflik, name='ders_aktiflik'),
    path('onay-bekleyenler/', views.onay_bekleyenler, name='onay_bekleyenler'),
    path('denemeler/<int:pk>/onayla/', views.deneme_onayla, name='deneme_onayla'),
    path('denemeler/<int:pk>/reddet/', views.deneme_reddet, name='deneme_reddet'),
    path('talepler/', views.talepler, name='talepler'),
    path('talepler/<int:pk>/kabul/', views.talep_kabul, name='talep_kabul'),
    path('talepler/<int:pk>/reddet/', views.talep_reddet, name='talep_reddet'),
    path('islem-gecmisi/', views.islem_gecmisi, name='islem_gecmisi'),
]
