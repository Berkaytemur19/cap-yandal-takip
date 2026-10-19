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
- [ ] Adım 7: README.md (sıfırdan kurulum + demo hesapları).

### Alınan tasarım kararları (kullanıcı onayladı)
- django-simple-history yerine kendi append-only `IslemKaydi` modelimiz.
- Teknik seçmeliler katalogda `SECMELI_HAVUZ` türünde yer tutucu ders; gerçek seçmeli eşleştirmesi sonra.
- YDP protokolü sentetik.
- "Listeden çıkarma" = `OgrenciDers.listede=False` (+gerekçe); "dersi bıraktı" = deneme durumu `CIKARILDI`.
- python-magic (Windows'ta `python-magic-bin`) belge özelliğiyle eklenecek.
- Öğrenci şimdilik yalnızca PLANLANDI/ALINDI girebilir; not girişi transkript yükleme özelliğiyle açılacak.
- Koordinatörün girdiği deneme doğrudan onaylı; öğrencininki BEKLIYOR.
- `takip` modelleri adminde salt okunur (değişiklik servis katmanından geçsin diye).

## Güvenlik

- Yetki kontrolü **her view'da sunucu tarafında** yapılır.
- Öğrenci URL değiştirerek başkasının kaydını **açamamalı** (testle doğrulanır).
- Sızma testleri (OWASP ZAP, bandit) **sadece yerel ortamda**; sonuçlar `docs/guvenlik.md`'ye yazılır.
