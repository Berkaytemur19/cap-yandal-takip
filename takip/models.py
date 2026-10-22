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

    @property
    def ozet_durum(self):
        """Ekranda gösterilecek tek satırlık durum: (kod, metin)."""
        if self.tamamlandi:
            muaf = any(d.durum == DenemeDurumu.MUAF for d in self.onayli_denemeler)
            return ('MUAF', 'Muaf') if muaf else ('GECTI', 'Geçti')
        if self.bekleyen_denemeler:
            return ('BEKLIYOR', 'Onay bekliyor')
        son = self.son_onayli_deneme
        if son:
            return (son.durum, son.get_durum_display())
        return ('YOK', 'Alınmadı')


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


class TalepDurumu(models.TextChoices):
    BEKLIYOR = 'BEKLIYOR', 'Bekliyor'
    KABUL = 'KABUL', 'Kabul edildi'
    RED = 'RED', 'Reddedildi'


class DersTalebi(SilinmezModel):
    """Öğrencinin ders listesinde olmayan bir ders için koordinatöre gönderdiği talep.

    Ders katalogdaysa `ders` seçilir; katalogda yoksa `istenen_ders` alanına yazılır.
    Öğrenci ders listesine kendisi ders ekleyemez; talep kabul edilince koordinatör ekler.
    """

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='ders_talepleri')
    ders = models.ForeignKey(Ders, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    istenen_ders = models.CharField('katalogda olmayan ders', max_length=200, blank=True)
    aciklama = models.TextField('açıklama')
    durum = models.CharField(max_length=10, choices=TalepDurumu.choices, default=TalepDurumu.BEKLIYOR)

    yanit = models.TextField('yanıt / gerekçe', blank=True)
    yanitlayan = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    yanit_tarihi = models.DateTimeField('yanıt tarihi', null=True, blank=True)
    eklenen_kalem = models.ForeignKey(
        OgrenciDers, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name='listeye eklenen ders',
    )

    class Meta:
        verbose_name = 'Ders talebi'
        verbose_name_plural = 'Ders talepleri'
        ordering = ['-olusturulma']

    def __str__(self):
        return f'{self.ogrenci.ogrenci_no} — {self.istenen_metin}'

    @property
    def istenen_metin(self):
        return str(self.ders) if self.ders_id else self.istenen_ders


# ---------------------------------------------------------------------------
# Belgeler
# ---------------------------------------------------------------------------

class BelgeTuru(models.TextChoices):
    KAYIT_FORMU = 'KAYIT_FORMU', 'İmzalı kayıt formu'
    DERS_SECIM_FORMU = 'DERS_SECIM_FORMU', 'İmzalı ders seçim formu'
    # ÇAP Md 7-1 / YDP Md 6-1: program için ayrı not belgesi düzenlenir. Dönem sonu notları
    # bu belge yüklenmeden onaya gönderilemez.
    TRANSKRIPT = 'TRANSKRIPT', 'ÇAP/YDP not belgesi (dönem sonu transkripti)'
    ANA_DAL_TRANSKRIPTI = 'ANA_DAL_TRANSKRIPTI', 'Ana dal transkripti (isteğe bağlı)'
    RESMI_YAZI = 'RESMI_YAZI', 'Resmî yazı (ör. yönetim kurulu kararı)'
    DIGER = 'DIGER', 'Diğer'


# Resmî yazıları yalnızca koordinatör yükler.
OGRENCI_BELGE_TURLERI = [(d, a) for d, a in BelgeTuru.choices if d != BelgeTuru.RESMI_YAZI]


# Bu türler bir döneme aittir; yüklerken dönem seçilmesi zorunludur.
DONEMLI_BELGE_TURLERI = {BelgeTuru.DERS_SECIM_FORMU, BelgeTuru.TRANSKRIPT}


class BelgeDurumu(models.TextChoices):
    BEKLIYOR = 'BEKLIYOR', 'Onay bekliyor'
    ONAYLANDI = 'ONAYLANDI', 'Onaylandı'
    REDDEDILDI = 'REDDEDILDI', 'Reddedildi'


class Belge(SilinmezModel):
    """Öğrencinin yüklediği belge. Silinmez; aynı belgenin yeni sürümü yeni kayıt olarak eklenir.

    Dosya web kökü dışında (KORUMALI_DOSYA_KOKU) rastgele bir adla saklanır;
    yalnızca yetki kontrollü view ile sunulur.
    """

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='belgeler')
    tur = models.CharField('belge türü', max_length=20, choices=BelgeTuru.choices)
    donem = models.ForeignKey(
        AkademikDonem, on_delete=models.PROTECT, null=True, blank=True, verbose_name='dönem',
    )
    surum = models.PositiveSmallIntegerField('sürüm', default=1)
    aciklama = models.CharField('açıklama', max_length=300, blank=True)

    dosya_yolu = models.CharField('dosya yolu', max_length=300, unique=True, editable=False)
    orijinal_ad = models.CharField('dosya adı', max_length=200)
    mime_turu = models.CharField('dosya türü', max_length=50)
    boyut = models.PositiveIntegerField('boyut (bayt)')
    sha256 = models.CharField(max_length=64)

    durum = models.CharField(max_length=10, choices=BelgeDurumu.choices, default=BelgeDurumu.BEKLIYOR)
    yukleyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    inceleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    inceleme_tarihi = models.DateTimeField('inceleme tarihi', null=True, blank=True)
    red_gerekcesi = models.TextField('ret gerekçesi', blank=True)

    class Meta:
        verbose_name = 'Belge'
        verbose_name_plural = 'Belgeler'
        ordering = ['ogrenci', 'tur', '-olusturulma']

    def __str__(self):
        donem = f' {self.donem}' if self.donem_id else ''
        return f'{self.ogrenci.ogrenci_no} — {self.get_tur_display()}{donem} (s{self.surum})'


class BelgeIstegi(SilinmezModel):
    """Koordinatörün öğrenciden istediği ek belge. Durum, yanıt olarak yüklenen belgeden çıkar:
    belge yoksa bekliyor; varsa belgenin durumu (yüklendi = onay bekliyor, onaylandı, reddedildi).
    Reddedilirse öğrenci yeni sürüm yükler; istek en son yüklenen belgeyi gösterir."""

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='belge_istekleri')
    tur = models.CharField('belge türü', max_length=20, choices=BelgeTuru.choices)
    donem = models.ForeignKey(
        AkademikDonem, on_delete=models.PROTECT, null=True, blank=True, verbose_name='dönem',
    )
    aciklama = models.TextField('açıklama')
    isteyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    belge = models.ForeignKey(Belge, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                              verbose_name='yüklenen belge')

    class Meta:
        verbose_name = 'Ek belge isteği'
        verbose_name_plural = 'Ek belge istekleri'
        ordering = ['-olusturulma']

    def __str__(self):
        donem = f' {self.donem}' if self.donem_id else ''
        return f'{self.ogrenci.ogrenci_no} — {self.get_tur_display()}{donem} isteği'

    DURUMLAR = {
        None: ('BEKLIYOR', 'Bekliyor'),
        BelgeDurumu.BEKLIYOR: ('YUKLENDI', 'Yüklendi'),
        BelgeDurumu.ONAYLANDI: ('ONAYLANDI', 'Onaylandı'),
        BelgeDurumu.REDDEDILDI: ('REDDEDILDI', 'Reddedildi'),
    }

    @property
    def durum(self):
        """(kod, metin): Bekliyor / Yüklendi / Onaylandı / Reddedildi."""
        return self.DURUMLAR[self.belge.durum if self.belge_id else None]

    @property
    def acik(self):
        """Öğrenci yanıt yükleyebilir mi: henüz yüklenmemiş ya da son yükleme reddedilmiş."""
        return self.durum[0] in ('BEKLIYOR', 'REDDEDILDI')


# ---------------------------------------------------------------------------
# Mesajlaşma
# ---------------------------------------------------------------------------

class MesajDegistirilemez(Exception):
    """Gönderilmiş mesajın içeriği değiştirilmeye çalışıldı."""


class Mesaj(SilinmezModel):
    """Koordinatör ile öğrenci arasındaki yazışma (öğrenci başına tek yazışma).

    Kalıcı kayıttır: silinemez, gönderildikten sonra yalnızca okunma zamanı işlenir.
    Ek dosya belgelerle aynı kontrolden geçer ve web kökü dışında saklanır.
    """

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name='mesajlar')
    gonderen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    metin = models.TextField()
    istek = models.ForeignKey(BelgeIstegi, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                              verbose_name='ilgili belge isteği')

    ek_yolu = models.CharField('ek dosya yolu', max_length=300, blank=True, editable=False)
    ek_adi = models.CharField('ek dosya adı', max_length=200, blank=True)
    ek_mime = models.CharField('ek dosya türü', max_length=50, blank=True)
    ek_boyut = models.PositiveIntegerField('ek boyutu (bayt)', null=True, blank=True)
    ek_sha256 = models.CharField(max_length=64, blank=True)

    okunma_tarihi = models.DateTimeField('okunma tarihi', null=True, blank=True)

    DEGISMEZ_ALANLAR = ['ogrenci_id', 'gonderen_id', 'metin', 'istek_id', 'ek_yolu', 'ek_adi', 'ek_mime',
                        'ek_boyut', 'ek_sha256']

    class Meta:
        verbose_name = 'Mesaj'
        verbose_name_plural = 'Mesajlar'
        ordering = ['olusturulma', 'pk']

    def __str__(self):
        return f'{self.ogrenci.ogrenci_no} — {self.gonderen.username}: {self.metin[:40]}'

    def save(self, *args, **kwargs):
        if self.pk:
            eski = Mesaj.objects.filter(pk=self.pk).values(*self.DEGISMEZ_ALANLAR).first()
            if eski and any(eski[a] != getattr(self, a) for a in self.DEGISMEZ_ALANLAR):
                raise MesajDegistirilemez('Gönderilmiş mesaj değiştirilemez.')
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Dönem sonu not girişi
# ---------------------------------------------------------------------------

class NotGirisi(SilinmezModel):
    """Öğrencinin onaylı 'alındı' kaydı için girdiği dönem sonu notu.

    Onaylı deneme kilitli olduğundan not doğrudan ona yazılmaz; bu ayrı kayıt onay bekler.
    Koordinatör transkriptle karşılaştırıp onaylayınca deneme Geçti/Kaldı olur. Reddedilen
    giriş silinmez, gerekçesiyle kalır; öğrenci düzeltip yeniden gönderebilir.
    """

    deneme = models.ForeignKey(DersDenemesi, on_delete=models.PROTECT, related_name='not_girisleri')
    harf_notu = models.CharField('harf notu', max_length=2, choices=HarfNotu.choices)
    # Geçme notu yönetmeliğe tabidir (ÇAP Md 8-a); koda gömülmez. Öğrenci transkriptte yazanı girer.
    durum = models.CharField(max_length=10, choices=[
        (DenemeDurumu.GECTI, DenemeDurumu.GECTI.label), (DenemeDurumu.KALDI, DenemeDurumu.KALDI.label),
    ])
    transkript = models.ForeignKey(
        Belge, on_delete=models.PROTECT, related_name='+', verbose_name='gönderildiği transkript',
    )
    onay_durumu = models.CharField(
        'onay durumu', max_length=10, choices=OnayDurumu.choices, default=OnayDurumu.BEKLIYOR,
    )
    giren = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    inceleyen = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    inceleme_tarihi = models.DateTimeField('inceleme tarihi', null=True, blank=True)
    red_gerekcesi = models.TextField('ret gerekçesi', blank=True)

    class Meta:
        verbose_name = 'Not girişi'
        verbose_name_plural = 'Not girişleri'
        ordering = ['olusturulma']

    def __str__(self):
        return f'{self.deneme} → {self.harf_notu} {self.get_durum_display()}'


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
