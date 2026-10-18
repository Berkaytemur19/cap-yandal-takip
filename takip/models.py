"""ÇAP / Yandal takip modelleri.

Kurallar:
- Hiçbir kayıt silinmez (SilinmezModel). Geçersiz kayıt "iptal" olarak işaretlenir.
- Veriyi değiştiren her işlem takip.services içinden yapılır ve IslemKaydi'na yazılır.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# ---------------------------------------------------------------------------
# Silinmez temel sınıf
# ---------------------------------------------------------------------------

class SilmeYasak(Exception):
    """Sistemde kayıt silinmeye çalışıldığında fırlatılır."""


class SilinmezQuerySet(models.QuerySet):
    def delete(self):
        raise SilmeYasak('Kayıtlar silinemez; iptal olarak işaretleyin.')


class SilinmezModel(models.Model):
    olusturulma = models.DateTimeField('oluşturulma', auto_now_add=True)
    guncellenme = models.DateTimeField('güncellenme', auto_now=True)

    objects = SilinmezQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise SilmeYasak('Kayıtlar silinemez; iptal olarak işaretleyin.')


# ---------------------------------------------------------------------------
# Seçenekler
# ---------------------------------------------------------------------------

class ProgramTuru(models.TextChoices):
    CAP = 'CAP', 'Çift Anadal (ÇAP)'
    YDP = 'YDP', 'Yandal (YDP)'


class DonemTuru(models.TextChoices):
    GUZ = 'GUZ', 'Güz'
    BAHAR = 'BAHAR', 'Bahar'
    YAZ = 'YAZ', 'Yaz'


class HarfNotu(models.TextChoices):
    AA = 'AA', 'AA'
    BA = 'BA', 'BA'
    BB = 'BB', 'BB'
    CB = 'CB', 'CB'
    CC = 'CC', 'CC'
    DC = 'DC', 'DC'
    DD = 'DD', 'DD'
    FD = 'FD', 'FD'
    FF = 'FF', 'FF'


# GANO hesabı için katsayılar (kural motoru sonraki oturumda kullanacak).
NOT_KATSAYISI = {
    'AA': Decimal('4.0'), 'BA': Decimal('3.5'), 'BB': Decimal('3.0'),
    'CB': Decimal('2.5'), 'CC': Decimal('2.0'), 'DC': Decimal('1.5'),
    'DD': Decimal('1.0'), 'FD': Decimal('0.5'), 'FF': Decimal('0.0'),
}


class DenemeDurumu(models.TextChoices):
    PLANLANDI = 'PLANLANDI', 'Planlandı'
    ALINDI = 'ALINDI', 'Alındı'
    GECTI = 'GECTI', 'Geçti'
    KALDI = 'KALDI', 'Kaldı'
    MUAF = 'MUAF', 'Muaf'
    CIKARILDI = 'CIKARILDI', 'Çıkarıldı'


class OnayDurumu(models.TextChoices):
    BEKLIYOR = 'BEKLIYOR', 'Onay bekliyor'
    ONAYLANDI = 'ONAYLANDI', 'Onaylandı'
    REDDEDILDI = 'REDDEDILDI', 'Reddedildi'
    IPTAL = 'IPTAL', 'İptal'


class KayitDurumu(models.TextChoices):
    AKTIF = 'AKTIF', 'Aktif'
    MEZUN = 'MEZUN', 'Mezun (ÇAP)'
    SERTIFIKA_ALDI = 'SERTIFIKA_ALDI', 'Sertifika aldı (YDP)'
    KAYDI_SILINDI = 'KAYDI_SILINDI', 'Kaydı silindi'
    IPTAL = 'IPTAL', 'İptal (hatalı kayıt)'


class DersTuru(models.TextChoices):
    ZORUNLU = 'ZORUNLU', 'Zorunlu'
    SECMELI_HAVUZ = 'SECMELI_HAVUZ', 'Seçmeli havuzu'


# ---------------------------------------------------------------------------
# Katalog ve dönem
# ---------------------------------------------------------------------------

class AkademikDonem(SilinmezModel):
    baslangic_yili = models.PositiveSmallIntegerField(
        'başlangıç yılı', validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        help_text='2025-2026 için 2025',
    )
    donem = models.CharField('dönem', max_length=5, choices=DonemTuru.choices)

    class Meta:
        verbose_name = 'Akademik dönem'
        verbose_name_plural = 'Akademik dönemler'
        ordering = ['baslangic_yili', 'donem']
        constraints = [
            models.UniqueConstraint(fields=['baslangic_yili', 'donem'], name='benzersiz_donem'),
        ]

    def __str__(self):
        return f'{self.baslangic_yili}-{self.baslangic_yili + 1} {self.get_donem_display()}'

    @property
    def sira(self):
        """Dönemleri kronolojik sıralamak için: Güz < Bahar < Yaz."""
        return (self.baslangic_yili, ['GUZ', 'BAHAR', 'YAZ'].index(self.donem))


class Ders(SilinmezModel):
    """Ders kataloğu. Silinmez, pasife alınır."""

    kod = models.CharField(max_length=20, unique=True)
    ad = models.CharField(max_length=200)
    akts = models.PositiveSmallIntegerField('AKTS', validators=[MinValueValidator(1), MaxValueValidator(60)])
    tur = models.CharField('tür', max_length=20, choices=DersTuru.choices, default=DersTuru.ZORUNLU)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Ders'
        verbose_name_plural = 'Ders kataloğu'
        ordering = ['kod']

    def __str__(self):
        return f'{self.kod} {self.ad}'


class Protokol(SilinmezModel):
    """Bir ana dal için ÇAP veya YDP ders planı. Öğrenci eklenince ders listesi buradan oluşur."""

    ad = models.CharField(max_length=200)
    program_turu = models.CharField('program türü', max_length=3, choices=ProgramTuru.choices)
    ana_dal_bolumu = models.CharField('ana dal bölümü', max_length=200)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Protokol'
        verbose_name_plural = 'Protokoller'

    def __str__(self):
        return self.ad


class ProtokolDersi(SilinmezModel):
    """Protokoldeki bir ders satırı. Seçmeli havuz dersi birden çok satırda tekrar edebilir."""

    protokol = models.ForeignKey(Protokol, on_delete=models.PROTECT, related_name='dersler')
    ders = models.ForeignKey(Ders, on_delete=models.PROTECT)
    yariyil = models.PositiveSmallIntegerField('yarıyıl', validators=[MinValueValidator(1), MaxValueValidator(8)])

    class Meta:
        verbose_name = 'Protokol dersi'
        verbose_name_plural = 'Protokol dersleri'
        ordering = ['protokol', 'yariyil', 'ders__kod']


# ---------------------------------------------------------------------------
# Öğrenci
# ---------------------------------------------------------------------------

class Ogrenci(SilinmezModel):
    kullanici = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ogrenci',
    )
    ogrenci_no = models.CharField('öğrenci no', max_length=20, unique=True)
    ad = models.CharField(max_length=100)
    soyad = models.CharField(max_length=100)
    okul_eposta = models.EmailField('okul e-postası', unique=True)
    program_turu = models.CharField('program türü', max_length=3, choices=ProgramTuru.choices)
    ana_dal_bolumu = models.CharField('ana dal bölümü', max_length=200)
    protokol = models.ForeignKey(Protokol, on_delete=models.PROTECT)
    kabul_donemi = models.ForeignKey(
        AkademikDonem, on_delete=models.PROTECT, related_name='+', verbose_name='kabul dönemi',
    )
    kayit_durumu = models.CharField(
        'kayıt durumu', max_length=20, choices=KayitDurumu.choices, default=KayitDurumu.AKTIF,
    )
    durum_gerekcesi = models.TextField('durum gerekçesi', blank=True)

    class Meta:
        verbose_name = 'Öğrenci'
        verbose_name_plural = 'Öğrenciler'
        ordering = ['ogrenci_no']

    def __str__(self):
        return f'{self.ogrenci_no} {self.ad_soyad}'

    @property
    def ad_soyad(self):
        return f'{self.ad} {self.soyad}'

    def ders_ozeti(self):
        """Ders listesinin AKTS özeti. Sadece onaylı denemeler hesaba girer."""
        kalemler = list(
            self.ders_listesi.filter(listede=True)
            .select_related('ders')
            .prefetch_related('denemeler__donem')
        )
        tamamlanan = [k for k in kalemler if k.tamamlandi]
        kalan = [k for k in kalemler if not k.tamamlandi]
        return {
            'toplam_akts': sum(k.ders.akts for k in kalemler),
            'tamamlanan_akts': sum(k.ders.akts for k in tamamlanan),
            'kalan_akts': sum(k.ders.akts for k in kalan),
            'tamamlanan_sayi': len(tamamlanan),
            'kalan_sayi': len(kalan),
            'bekleyen_sayi': sum(len(k.bekleyen_denemeler) for k in kalemler),
        }


class AnaDalGanoKaydi(SilinmezModel):
    """Ana dal GANO'su. Yalnızca koordinatör girer, kaynağını yazar. Geçmiş tutulur (Md 9e için)."""

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='gano_kayitlari')
    donem = models.ForeignKey(AkademikDonem, on_delete=models.PROTECT, verbose_name='dönem')
    gano = models.DecimalField(
        'GANO', max_digits=3, decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('4'))],
    )
    kaynak = models.CharField(max_length=300, help_text='Örn: OBİS transkripti, 12.02.2026')
    giren = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    iptal = models.BooleanField(default=False)
    iptal_gerekcesi = models.TextField('iptal gerekçesi', blank=True)

    class Meta:
        verbose_name = 'Ana dal GANO kaydı'
        verbose_name_plural = 'Ana dal GANO kayıtları'
        ordering = ['ogrenci', 'donem__baslangic_yili', 'olusturulma']


# ---------------------------------------------------------------------------
# Ders takibi (merkez)
# ---------------------------------------------------------------------------

class OgrenciDers(SilinmezModel):
    """Öğrencinin ders listesindeki bir kalem.

    Koordinatör listeden çıkardığında kayıt silinmez; listede=False olur ve gerekçe tutulur.
    """

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='ders_listesi')
    ders = models.ForeignKey(Ders, on_delete=models.PROTECT)
    yariyil = models.PositiveSmallIntegerField('önerilen yarıyıl', null=True, blank=True)
    listede = models.BooleanField(default=True)

    ekleme_gerekcesi = models.TextField('ekleme gerekçesi', blank=True)
    ekleyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    cikarma_gerekcesi = models.TextField('çıkarma gerekçesi', blank=True)
    cikaran = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    cikarilma_tarihi = models.DateTimeField('çıkarılma tarihi', null=True, blank=True)

    class Meta:
        verbose_name = 'Öğrenci ders listesi kalemi'
        verbose_name_plural = 'Öğrenci ders listesi'
        ordering = ['ogrenci', 'yariyil', 'ders__kod']

    def __str__(self):
        return f'{self.ogrenci.ogrenci_no} — {self.ders}'

    # Not: aşağıdaki özellikler prefetch_related('denemeler') ile birlikte verimli çalışır.
    @property
    def onayli_denemeler(self):
        return [d for d in self.denemeler.all() if d.onay_durumu == OnayDurumu.ONAYLANDI]

    @property
    def bekleyen_denemeler(self):
        return [d for d in self.denemeler.all() if d.onay_durumu == OnayDurumu.BEKLIYOR]

    @property
    def tamamlandi(self):
        return any(d.durum in (DenemeDurumu.GECTI, DenemeDurumu.MUAF) for d in self.onayli_denemeler)

    @property
    def son_onayli_deneme(self):
        denemeler = sorted(self.onayli_denemeler, key=lambda d: (d.donem.sira, d.olusturulma))
        return denemeler[-1] if denemeler else None


class DenemeKilitli(Exception):
    """Onaylanmış denemeyi düzeltme servisi dışında değiştirme girişimi."""


class DersDenemesi(SilinmezModel):
    """Bir dersin bir dönemdeki tek alınışı. Aynı ders tekrar alınırsa yeni kayıt açılır."""

    liste_kalemi = models.ForeignKey(OgrenciDers, on_delete=models.PROTECT, related_name='denemeler')
    donem = models.ForeignKey(AkademikDonem, on_delete=models.PROTECT, verbose_name='dönem')
    harf_notu = models.CharField('harf notu', max_length=2, choices=HarfNotu.choices, blank=True)
    durum = models.CharField(max_length=10, choices=DenemeDurumu.choices, default=DenemeDurumu.PLANLANDI)
    onay_durumu = models.CharField(
        'onay durumu', max_length=10, choices=OnayDurumu.choices, default=OnayDurumu.BEKLIYOR,
    )
    geriye_donuk = models.BooleanField(
        'geriye dönük giriş', default=False,
        help_text='Koordinatörün mevcut öğrenci için girdiği eski ders; onay kilidine takılmaz.',
    )

    giren = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    onaylayan = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    onay_tarihi = models.DateTimeField('onay tarihi', null=True, blank=True)
    red_gerekcesi = models.TextField('ret gerekçesi', blank=True)
    iptal_gerekcesi = models.TextField('iptal gerekçesi', blank=True)

    class Meta:
        verbose_name = 'Ders denemesi'
        verbose_name_plural = 'Ders denemeleri'
        ordering = ['liste_kalemi', 'donem__baslangic_yili', 'olusturulma']

    def __str__(self):
        return f'{self.liste_kalemi} / {self.donem} / {self.get_durum_display()}'

    def save(self, *args, **kwargs):
        # Onaylı kayıt kilitlidir. Yalnızca services.deneme_duzelt / deneme_iptal kilidi açar.
        if self.pk and not getattr(self, '_kilit_acik', False):
            eski_onay = DersDenemesi.objects.filter(pk=self.pk).values_list('onay_durumu', flat=True).first()
            if eski_onay == OnayDurumu.ONAYLANDI:
                raise DenemeKilitli('Onaylanmış kayıt kilitlidir; düzeltmeyi koordinatör yapar.')
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Kural ayarları (sürümlü)
# ---------------------------------------------------------------------------

class KuralAyari(SilinmezModel):
    """Yönerge eşikleri. Değer değişince eski satır güncellenmez, yeni sürüm eklenir."""

    anahtar = models.CharField(max_length=60, help_text='Örn: cap.mezuniyet_gano')
    program_turu = models.CharField('program türü', max_length=3, choices=ProgramTuru.choices)
    deger = models.DecimalField('değer', max_digits=8, decimal_places=2)
    aciklama = models.CharField('açıklama', max_length=300)
    madde = models.CharField(max_length=20, help_text='Yönerge maddesi, örn: 8c')
    surum = models.PositiveIntegerField('sürüm')
    olusturan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        verbose_name = 'Kural ayarı'
        verbose_name_plural = 'Kural ayarları'
        ordering = ['program_turu', 'anahtar', '-surum']
        constraints = [
            models.UniqueConstraint(fields=['anahtar', 'surum'], name='benzersiz_kural_surumu'),
        ]

    def __str__(self):
        return f'{self.anahtar} = {self.deger} (s{self.surum})'

    @classmethod
    def guncel(cls, anahtar):
        return cls.objects.filter(anahtar=anahtar).order_by('-surum').first()


# ---------------------------------------------------------------------------
# İşlem kaydı (append-only)
# ---------------------------------------------------------------------------

class IslemKaydiQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise SilmeYasak('İşlem kayıtları değiştirilemez.')

    def delete(self):
        raise SilmeYasak('İşlem kayıtları silinemez.')


class IslemKaydi(models.Model):
    """Kim, ne zaman, neyi, eski ve yeni değer. Yalnızca eklenir; güncellenemez, silinemez."""

    zaman = models.DateTimeField(auto_now_add=True, db_index=True)
    kullanici = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name='kullanıcı',
    )
    islem = models.CharField('işlem', max_length=60)
    model_adi = models.CharField('model', max_length=60)
    nesne_id = models.CharField('nesne no', max_length=40)
    nesne_metni = models.CharField('nesne', max_length=300)
    eski_deger = models.JSONField('eski değer', null=True, blank=True)
    yeni_deger = models.JSONField('yeni değer', null=True, blank=True)
    aciklama = models.TextField('açıklama', blank=True)

    objects = IslemKaydiQuerySet.as_manager()

    class Meta:
        verbose_name = 'İşlem kaydı'
        verbose_name_plural = 'İşlem kayıtları'
        ordering = ['-zaman', '-id']

    def __str__(self):
        return f'{self.zaman:%d.%m.%Y %H:%M} {self.kullanici} {self.islem} {self.nesne_metni}'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise SilmeYasak('İşlem kayıtları değiştirilemez.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise SilmeYasak('İşlem kayıtları silinemez.')
