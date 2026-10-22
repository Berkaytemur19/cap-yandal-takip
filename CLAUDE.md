# ÇAP / Yandal Takip Sistemi — Proje Bilgileri

Selçuk Üniversitesi Bilgisayar Mühendisliği bölümüne gelen **çift anadal (ÇAP)** ve **yandal (YDP)** öğrencilerini takip eden web uygulaması.
Ders projesi, tek geliştirici. Geliştirici Python/Django'yu yeni öğreniyor: **her adımda ne yapıldığını kısaca açıkla, çalıştırılacak komutları açıkça ver.**

- **Demo teslimi:** 30 Ekim 2026
- **Ortam:** Windows (PowerShell), Python 3.14, Git

## Teknoloji

- Python 3 + Django
- Django şablonları + Bootstrap 5 (sade arayüz)
- SQLite
- Git
- İşlem geçmişi: `django-simple-history` veya append-only `AuditLog`
- Dosya kontrolü: `python-magic` + boyut sınırı
- Giriş denemesi sınırı: `django-axes`

## Kapsam

- Sistem **yalnızca bu bölüm** için.
- Başvuru değerlendirme ve öğrenci seçimi sistemde **yapılmaz**; koordinatör kabul edilen öğrenciyi sisteme ekler.
- Öğrencinin ana dal dersleri takip edilmez. Ana dal GANO'sunu **yalnızca koordinatör** girer ve **kaynağını** yazar.
- Öğrenci ya ÇAP ya YDP olarak kayıtlıdır (ikisi birden değil).
- OBİS bağlantısı yok, veriler manuel girilir. Ancak:
  - Tüm veri girişi **tek bir servis katmanından** geçer.
  - **Öğrenci no benzersiz anahtar.**
  - İleride CSV/OBİS'ten veri alınabilecek şekilde tasarla.
- **Sadece sentetik veri** kullanılır.

## Roller (yalnızca üç)

### Koordinatör (yönetici)
- Öğrenci ekler (öğrenci no, ad-soyad, okul e-postası, ÇAP/YDP, kabul dönemi) ve hesabını açar.
- Kayıt ve belgeleri onaylar veya **gerekçeli** reddeder; ek belge ister.
- Öğrenci kartına öğrencinin **görmediği** not ekler.
- Kural ayarlarını günceller.
- Kaydı düzeltir veya gerekçeli iptal eder.
- Mezuniyet / sertifika / kayıt silme kararını verir.

### Öğrenci
- **Yalnızca kendi** bilgilerini görür.
- İmzalı formlarını yükler.
- Alacağı dersleri **katalogdan** seçer (serbest metinle ders giremez; katalogda yoksa talep gönderir).
- Her dönem aldığı dersleri ve dönem sonu notlarını girer; transkript yükler.
- Koordinatörle mesajlaşır.
- Aldığı / geçtiği / kalan dersleri ve onay bekleyenleri görür.
- **Kendi kendine kayıt olamaz.**

### Bölüm Başkanı
- **Sadece izler**: kayıtları ve işlem geçmişini görür, hiçbir şeyi değiştiremez.

## İş Kuralları

- **Onay akışı:** Öğrencinin girdiği ders/not/belge "onay bekliyor" başlar, onaylanana kadar hesaplara girmez. Onaylanan kayıt **kilitlenir**; düzeltmeyi yalnızca koordinatör yapar ve işlem kaydına geçer.
- **Hiçbir şey silinmez**; geçersiz kayıt "iptal" olarak işaretlenir.
- **İşlem kaydı (audit):** kim, ne zaman, neyi, eski değer, yeni değer. Değiştirilemez; bölüm başkanı görür.
- **Ders takibi (sistemin merkezi):**
  - Öğrenci başına ders listesi.
  - Her ders için: akademik yıl + dönem (ör. 2025-2026 Güz), not, durum.
  - Durumlar: `planlandı`, `alındı`, `geçti`, `kaldı`, `muaf`, `çıkarıldı`.
  - Aynı ders birden çok kez alınabilir; **her deneme ayrı kayıt**.
  - Tamamlanan ve kalan dersler **AKTS** ile görünür.
  - Koordinatör listeye ders ekleyip çıkarabilir; gerekçe ve tarihle kaydedilir; **geçilmiş derslere dokunmaz**.
- **Ders kataloğu:** koordinatör ekler, günceller, pasife alır (silmez).
- **Belgeler:**
  - Tür ve durum (`bekliyor`, `onaylandı`, `reddedildi`).
  - Eski sürümler kalır; öğrenci silemez.
  - Dosya türü ve boyut kontrolü.
  - Dosyalar **web kökü dışında** saklanır, **yetki kontrollü** sunulur.
  - Dönem sonu transkripti yüklenmeden notlar onaya gönderilemez.
- **Mesajlaşma:** koordinatör ↔ öğrenci, ekli dosya, silinemez, yeni mesaj bildirimi.
- **Kural eşikleri koda gömülmez**: ayarlardan gelir ve **sürümlüdür**, eski sürümler kalır. Kurallar **sadece onaylı kayıtlarla** hesaplanır ve **sadece UYARI** üretir (otomatik işlem yapmaz).
- Mevcut öğrencilerin eski dersleri koordinatör tarafından **geriye dönük** girilebilir; onay kilidine takılmaz.

## Yönerge Kuralları (seed ayar değerleri)

### ÇAP
| Kural | Değer | Madde |
|---|---|---|
| Ana dal GANO bir kez 2.50'ye kadar düşebilir; ikinci kez 2.72 altı → kayıt silme uyarısı | 2.72 / 2.50 | Md 9e |
| Mazeretsiz iki dönem ders almama → uyarı | 2 dönem | 9d |
| Mezuniyet için ana dal GANO | ≥ 2.72 | 8c |
| Toplam AKTS | 240 | 7-2 |
| Azami süre | 7 yıl | 8d |

### YDP
| Kural | Değer | Madde |
|---|---|---|
| En az AKTS ve ders sayısı | 30 AKTS, 6 ders | 5g |
| İki dönem ders almama → uyarı | 2 dönem | 7-4 |
| Ana dal GANO < 2.30 → uyarı | 2.30 | 7-5 |
| Yandal GANO iki dönem < 2.00 → uyarı | 2.00 | 7-6 |
| Sertifika: ana daldan mezun + yandal GANO ≥ 2.00 | 2.00 | 7-8 |
| En çok iki yarıyıl ek süre | 2 yarıyıl | 7-9 |

## Örnek Protokol: EEM → Bilgisayar Müh. ÇAP (toplam 135 AKTS)

| Kod | AKTS | Ders |
|---|---|---|
| 3301156 | 4 | Bilgisayar Mühendisliğine Giriş |
| 3301351 | 4 | Nesneye Yönelik Programlama Dili |
| 3301352 | 4 | İşletim Sistemleri |
| 3301354 | 4 | Veri Yapıları ve Uygulamaları |
| 3301452 | 4 | Programlama Dili-2 |
| 3301454 | 5 | Veri Tabanı Yönetim Sistemleri |
| 3301455 | 4 | Yazılım Mühendisliği |
| 3301456 | 4 | Mobil Programlama |
| 3301552 | 5 | Programlama Dili-3 |
| 3301553 | 5 | Veri Haberleşmesi ve Ağlar |
| — | 3 × 4 | 5. Yarıyıl Teknik Seçmeli |
| 3301651 | 4 | Yapay Zeka |
| 3301652 | 4 | Otomata Teorisi ve Biçimsel Diller |
| 3301653 | 4 | Görüntü İşleme |
| 3301654 | 6 | Mühendislik Tasarımı |
| — | 3 × 4 | 6. Yarıyıl Teknik Seçmeli |
| 3301751 | 4 | Bilgisayar Mühendisliği Uygulamaları |
| 3301752 | 4 | Bilgisayar Mimarisi ve Organizasyonu |
| 3301753 | 4 | Veri Bilimi |
| — | 2 × 4 | 7. Yarıyıl Teknik Seçmeli |
| 3301851 | 20 | İşletmede Mesleki Eğitim |
| 3301852 | 5 | Staj 1 |
| 3301853 | 5 | Staj 2 |

## İlerleme Durumu (ilk sürüm oturumu — 19 Ekim 2026)

Oturum hedefi (7 adım): 1) git/venv/requirements/Django, 2) üç rollü kullanıcı, 3) modeller, 4) ekranlar, 5) yetki testleri, 6) `seed_demo` komutu, 7) README.

- [x] Adım 1–2: iskelet + `hesaplar.Kullanici` (rol alanı), `hesaplar/yetki.py` → `rol_gerekli` — commit `2a9d9d7`
- [x] Adım 3: `takip/models.py`, `takip/services.py` (tek yazma kapısı + IslemKaydi), servis testleri (14 test geçti) — commit `b90869e`
- [x] Adım 4: ekranlar — 20/20 test geçti, Bootstrap SRI hash'leri doğrulandı, kullanıcı runserver ile elle baktı (19 Ekim). Not: temiz kurulumda önce `manage.py migrate` gerekir (README'ye ve seed_demo akışına eklenecek).
- [x] Adım 5: `takip/tests/test_yetki.py` (11 test; toplam 31 geçti) — anonim → giriş yönlendirmesi; öğrenci başkasının detayı ve yönetim sayfaları → 403; başkan/öğrenci POST'ları → 403 ve veri + IslemKaydi değişmiyor; rolsüz hesap → 403; `ders_aktiflik` GET → 405. Testlerin gerçekten yakaladığı, korumayı geçici bozarak doğrulandı.
- [x] Adım 6: `seed_demo` komutu + `takip/tests/test_seed_demo.py` (9 test; toplam 40 geçti). Servis katmanından: 23 ders (TS5/TS6/TS7 havuz), ÇAP protokolü (135 AKTS), sentetik Makine→Bilgisayar yandal (7 ders, 30 AKTS), 13 kural ayarı, 4 öğrenci (2 ÇAP, 2 YDP; geriye dönük dersler, GANO, listeden çıkarma, 4 onay bekleyen öğrenci girişi). Demo hesapları: `koordinator`, `baskan`, öğrenci no'ları; şifre `Demo.2026`. Tekrar çalıştırılabilir (var olanı atlar, var olan kural ayarına dokunmaz); DEBUG kapalıyken çalışmaz. Gerçek db'ye yüklendi.
- [x] Adım 7: README.md (kurulum, demo hesapları, testler, roller, yapı, durum, sorun giderme). Kurulum adımları temiz bir klonda baştan sona denendi: migrate + seed_demo + 40 test OK.

**İlk sürüm oturumunun 7 adımı tamamlandı (19 Ekim 2026).** Sıradaki özellikler README'deki "Henüz yapılmayanlar" listesinde. GitHub (gizli repo): https://github.com/Berkaytemur19/cap-yandal-takip

## Hoca geri bildirimi sonrası (20–21 Ekim 2026)

Hoca (20 Ekim): öğrencinin ders seçeceği sayfa ve form yükleyeceği sayfa olmalı; en sonda deploy (Vercel dedi — Vercel Django+SQLite+dosya yükleme için uygun değil, PythonAnywhere önerildi, hocaya sorulacak).

- [x] Onay bekleyenler ekranı (onayla / gerekçeli reddet) — commit `528bb3a` (kullanıcı elle bakmayı sona bıraktı)
- [x] Ders seçimi + ders talepleri: `services.ders_sec` / `talep_gonder` / `talep_kabul` / `talep_reddet`, `DersTalebi` modeli (migration 0002), `/benim/ders-sec/` (öğrenci), `/talepler/` (koordinatör), seed'de Zeynep için 1 bekleyen talep, `test_ders_secimi.py` (71 test geçti)
- [x] Belge yükleme: `Belge` modeli (migration 0003), `services.belge_yukle` / `belge_onayla` / `belge_reddet` / `dosya_kontrol`, `/benim/belgeler/` (öğrenci), `/belgeler/` (koordinatör), `/belgeler/<pk>/dosya/` (yetkili indirme), öğrenci detayında belge tablosu, seed'de Elif için bekleyen sentetik PDF, `test_belgeler.py` (91 test geçti; sahiplik kontrolü bozulunca testin yakaladığı doğrulandı)
- [x] **22 Ekim — hocanın yeni maili:** ara sınav notu **canlı uygulama** üzerinden verilecek. 30 Ekim 23.59'a kadar ilkerozkan@selcuk.edu.tr adresine, konu "ÇAP Takip Otomasyonu Arasına - Ad soyad" ile canlı link + 3 rolün test hesapları + GitHub linki + geliştirme durumu gönderilecek. Bu yüzden deploy öne alındı. Platform: **PythonAnywhere** (kullanıcı onayladı).
- [x] Deploy hazırlığı: `.env` (python-dotenv, örnek `.env.ornek`), DEBUG kapalıyken gizli anahtar zorunlu + güvenli çerezler + HTTPS yönlendirme, `STATIC_ROOT=staticfiles`, axes için `hesaplar.yetki.istemci_ip` (proxy arkasında X-Real-IP), `seed_demo --canli`, README'de PythonAnywhere adımları (94 test geçti)
- [x] **Canlıda (22 Ekim): https://berkaytemur.pythonanywhere.com** — PythonAnywhere kullanıcı `berkaytemur`, Python 3.13, proje `/home/berkaytemur/cap-yandal-takip`, `.env` sunucuda. Dışarıdan doğrulandı: HTTPS yönlendirme, statik dosyalar, 3 rolle giriş ve yetkiler (başkan/öğrenci 403), belge indirme yetkisi. Güncelleme adımları README → "Canlıya alma". Repo artık herkese açık.
- [x] Koordinatör ekranları: öğrenci kartında GANO formu + listeye ders ekle; `/liste/<pk>/` (kalem_detay: kayıt gir/geriye dönük, düzelt, iptal, listeden çıkar); `/kurallar/` (başkan salt okunur). `test_koordinator_islemleri.py` (113 test geçti; yetki bozulunca testin yakaladığı doğrulandı)
- [x] Mesajlaşma + ek belge isteği + koordinatörün belge yüklemesi (migration 0005): `Mesaj` (öğrenci başına tek yazışma; değiştirilemez — `save` DEGISMEZ_ALANLAR kontrolü; yalnızca `okunma_tarihi` işlenir), `BelgeIstegi` (durum yüklenen belgeden türetilir), `BelgeTuru.RESMI_YAZI` (yalnız koordinatör), `services._SaklananDosya` (belge + mesaj eki ortak), `belge_yukle(..., ogrenci=, istek=)`, context processor `takip.context_processors.bildirimler` (menü rozeti), seed'de `YAZISMALAR`. Bölüm başkanı yazışmaları okur, yazamaz, okundu yapmaz. Bildirim yalnızca uygulama içi (e-posta yok — sunucuda SMTP yok). `test_mesajlasma.py` (155 test). **Canlıya alırken `migrate` + `seed_demo --canli`.**
- [ ] Eksik analizi (22 Ekim) — kalanlar: mezuniyet/sertifika/kayıt silme kararı, koordinatör özel notu, şifre değiştirme, sızma testi/güvenlik açıklaması
- [x] Not girişi: `NotGirisi` modeli (migration 0004), `services.not_girilebilir_denemeler` / `donem_transkripti` / `not_gir` / `not_onayla` / `not_reddet`, `/benim/notlar/` (öğrenci), "Onay bekleyenler"de notlar bölümü (not belgesine bağlantı), belge türleri: TRANSKRIPT = "ÇAP/YDP not belgesi", yeni ANA_DAL_TRANSKRIPTI (isteğe bağlı), seed'de `NOT_SENARYOLARI` (Burak bekleyen not, Zeynep belgesiz), `test_not_girisi.py` (134 test; transkript şartı bozulunca testin yakaladığı doğrulandı). **Canlıya alırken `migrate` + `seed_demo --canli` gerekir.**
- [ ] Kural uyarıları, mesajlaşma (zaman kalırsa)
- [ ] Deploy (en son)
- [ ] Kullanıcı en sonda elle kontrol edecek: onay ekranı, ders seçimi, talepler

### Alınan tasarım kararları (kullanıcı onayladı)
- django-simple-history yerine kendi append-only `IslemKaydi` modelimiz.
- Teknik seçmeliler katalogda `SECMELI_HAVUZ` türünde yer tutucu ders; gerçek seçmeli eşleştirmesi sonra.
- YDP protokolü sentetik.
- "Listeden çıkarma" = `OgrenciDers.listede=False` (+gerekçe); "dersi bıraktı" = deneme durumu `CIKARILDI`.
- python-magic (Windows'ta `python-magic-bin`) belge özelliğiyle eklenecek.
- Öğrenci şimdilik yalnızca PLANLANDI/ALINDI girebilir; not girişi transkript yükleme özelliğiyle açılacak.
- Koordinatörün girdiği deneme doğrudan onaylı; öğrencininki BEKLIYOR.
- `takip` modelleri adminde salt okunur (değişiklik servis katmanından geçsin diye).
- Ders seçimi: öğrenci yalnızca kendi listesindeki, tamamlanmamış, katalogda aktif derslerden seçer. Seçilebilir dönemler tarihten hesaplanır (Eylül–Ocak Güz, Şubat–Haziran Bahar, Temmuz–Ağustos Yaz): şimdiki dönem → ALINDI, sonraki dönem (yaz atlanır) → PLANLANDI. Her seçim BEKLIYOR deneme.
- Not girişi (yönergeler kontrol edildi, 22 Ekim): onaylı deneme kilitli olduğu için not ayrı `NotGirisi` kaydı olarak onay bekler; onaylanınca deneme GECTI/KALDI + harf notu olur (`deneme_not_isle` işlem kaydı). Yalnızca onaylı ALINDI, listede, dönemi şimdiki veya geçmiş olan denemeye girilir. Dönemin **ÇAP/YDP not belgesi** (ÇAP Md 7-1, YDP Md 6-1: ayrı not belgesi) yüklenmiş ve son sürümü reddedilmemiş olmalı (onay şartı yok — hoca "yüklenmeden gönderilemez" dedi). Ana dal transkripti isteğe bağlı, şartı karşılamaz. Geçme notu koda gömülmez (ÇAP Md 8-a: yönetmeliğe tabi): öğrenci harf notu + Geçti/Kaldı'yı transkriptteki gibi girer.
- Sonraki adım için not (yönergeden): Rehber, yönetmelik Md 17/4'ten ÇAP program not ortalaması ≥ 70/100 (bir kez 65'e düşebilir) aktarıyor — kural tablosunda yok, uyarılar adımında eklenecek. Yandal GANO (≥ 2.00) için harf notu katsayıları (AA=4.0 … FF=0) kural ayarı olarak tutulacak.
- Belge: türler KAYIT_FORMU, DERS_SECIM_FORMU, TRANSKRIPT, DIGER; DERS_SECIM_FORMU ve TRANSKRIPT dönem ister.PDF/JPG/PNG, 5 MB (ayarlar: `BELGE_AZAMI_BOYUT`, `BELGE_IZINLI_TURLER`). Dosya `KORUMALI_DOSYA_KOKU/belgeler/<ogrenci_no>/<uuid>.<uzantı>`; sha256 tutulur. Aynı tür+dönemde önceki sürüm BEKLIYOR iken yeni sürüm yüklenemez; onay/ret sonrası yeni sürüm (surum+1) eklenir. Yalnızca öğrenci yükler. "Ek belge isteme" şimdilik ret gerekçesiyle yapılıyor.
- Listede olmayan ders → `DersTalebi` (katalogdan ders VEYA serbest metin ad, açıklama zorunlu). Kabulde koordinatör katalogdan dersi seçer, `listeye_ders_ekle` çağrılır. Katalogda yoksa önce kataloğa ekler.

## Güvenlik

- Yetki kontrolü **her view'da sunucu tarafında** yapılır.
- Öğrenci URL değiştirerek başkasının kaydını **açamamalı** (testle doğrulanır).
- Sızma testleri (OWASP ZAP, bandit) **sadece yerel ortamda**; sonuçlar `docs/guvenlik.md`'ye yazılır.
