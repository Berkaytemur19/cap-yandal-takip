# ÇAP / Yandal Takip Sistemi

Selçuk Üniversitesi Bilgisayar Mühendisliği bölümüne gelen **çift anadal (ÇAP)** ve **yandal (YDP)**
öğrencilerinin ders ilerlemesini takip eden web uygulaması. Ders projesidir; içindeki tüm kişi ve not
verileri **sentetiktir**.

- Python 3 + Django 5.2, Django şablonları + Bootstrap 5, SQLite
- Giriş denemesi sınırı: `django-axes`
- Dosya türü kontrolü: `python-magic` (Windows'ta `python-magic-bin`, libmagic içinde gelir)
- Her değişiklik değiştirilemez bir **işlem kaydına** (kim / ne zaman / eski değer / yeni değer) yazılır.

## Kurulum (Windows, PowerShell)

Gerekenler: **Python 3.10 veya üstü** (3.14 ile denendi) ve Git.

```powershell
# 1. Projeyi indir ve klasörüne gir
git clone https://github.com/Berkaytemur19/cap-yandal-takip.git
cd cap-yandal-takip

# 2. Sanal ortamı kur ve paketleri yükle
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Veritabanı tablolarını oluştur
.\.venv\Scripts\python.exe manage.py migrate

# 4. Demo verisini yükle (dersler, protokoller, kural ayarları, demo hesapları, öğrenciler)
.\.venv\Scripts\python.exe manage.py seed_demo

# 5. Sunucuyu başlat
.\.venv\Scripts\python.exe manage.py runserver
```

Tarayıcıda **http://127.0.0.1:8000/giris/** adresini açın. Sunucuyu durdurmak için terminalde `Ctrl+C`.

> Komutlar sanal ortamın Python'unu doğrudan çağırır (`.\.venv\Scripts\python.exe`), böylece
> `Activate.ps1` ve PowerShell çalıştırma ilkesi (execution policy) ayarıyla uğraşmak gerekmez.

**macOS / Linux:** `.\.venv\Scripts\python.exe` yerine `.venv/bin/python` yazın; geri kalan adımlar aynı.
Dosya kontrolü için sistemde libmagic olmalı: macOS'ta `brew install libmagic`, Ubuntu'da `sudo apt install libmagic1`.

## Demo hesapları

`seed_demo` aşağıdaki hesapları açar. **Hepsinin şifresi: `Demo.2026`**

| Kullanıcı adı | Rol | Görebildikleri |
|---|---|---|
| `koordinator` | Koordinatör | Her şey; öğrenci ve ders ekler, kataloğu düzenler |
| `baskan` | Bölüm Başkanı | Öğrenciler ve işlem geçmişi — **yalnızca izler**, değiştiremez |
| `24330101` | Öğrenci — Elif Yılmaz (ÇAP) | Yalnızca kendi kaydı. Kaldığı dersi tekrar alıyor (aynı ders, iki deneme) |
| `25330102` | Öğrenci — Burak Kaya (ÇAP) | Muaf olduğu ders ve gerekçeyle listeden çıkarılmış ders |
| `25330201` | Öğrenci — Zeynep Arslan (YDP) | Yandal öğrencisi |
| `26330202` | Öğrenci — Emre Çelik (YDP) | Yeni kabul, henüz dersi yok |

Öğrencilerin bu dönem kendi girdiği 4 ders **onay bekliyor** durumundadır (koordinatör → "Onay bekleyenler").
Zeynep'in listesinde olmayan bir ders için gönderdiği 1 **ders talebi** yanıt bekler (koordinatör → "Ders talepleri").
Elif'in yüklediği imzalı kayıt formu (sentetik PDF) **onay bekler** (koordinatör → "Belgeler").

- `seed_demo` tekrar çalıştırılabilir: var olan kayıtları atlar, hiçbir şeyi çoğaltmaz.
- Bilinen şifreler kullandığı için yalnızca geliştirme modunda (`DEBUG` açık) çalışır.
- Kendi yönetici hesabınızı açmak için: `.\.venv\Scripts\python.exe manage.py createsuperuser`
  (rol sorusuna `KOORDINATOR`, `BOLUM_BASKANI` veya `OGRENCI` yazın).

## Testler

```powershell
.\.venv\Scripts\python.exe manage.py test
```

91 test; şunları doğrular:

- **Servis katmanı:** iş kuralları (onay kilidi, gerekçe zorunluluğu, silme yasağı, kural ayarı sürümleri).
- **Ekranlar:** her rol kendi sayfalarını açabiliyor; öğrenci ekleme ve katalog işlemleri çalışıyor.
- **Yetki:** öğrenci URL'deki numarayı değiştirerek başkasının kaydını açamıyor; bölüm başkanı ve öğrenci
  doğrudan POST isteğiyle veri değiştiremiyor (403, veritabanı ve işlem kaydı değişmiyor).
- **Ders seçimi ve talepler:** öğrenci yalnızca kendi listesinden ve izin verilen dönemlerde seçebiliyor;
  talep kabul edilince ders listeye ekleniyor; öğrenci ve bölüm başkanı talep yanıtlayamıyor.
- **Belgeler:** uzantısı `.pdf` yapılmış `.exe` gibi sahte dosyalar ve büyük dosyalar reddediliyor, diske
  yazılmıyor; yeni sürüm eskisini silmiyor; öğrenci başkasının belgesini açamıyor, giriş yapmayan hiç açamıyor.
- **Demo verisi:** `seed_demo` beklenen veriyi kuruyor ve ikinci çalıştırmada çoğaltmıyor.

## Roller

| Rol | Yetki |
|---|---|
| **Koordinatör** | Öğrenci ekler ve hesabını açar, ders kataloğunu yönetir, ders kayıtlarını ve belgeleri onaylar / gerekçeyle reddeder, ders taleplerini yanıtlar |
| **Bölüm Başkanı** | Kayıtları ve işlem geçmişini görür; hiçbir şeyi değiştiremez |
| **Öğrenci** | Yalnızca kendi ders listesini ve ilerlemesini görür; listesinden ders seçer, listesinde olmayan ders için talep gönderir; imzalı form ve transkript yükler; kendi kendine kayıt olamaz |

Yetki her sayfada **sunucu tarafında** kontrol edilir (`hesaplar/yetki.py` → `rol_gerekli`); servis
katmanı da aynı kontrolü ayrıca yapar.

## Temel kurallar

- **Hiçbir kayıt silinmez.** Geçersiz kayıt "iptal" olarak işaretlenir; ders kataloğundan ders pasife alınır.
- Öğrencinin girdiği ders kaydı **onay bekliyor** olarak başlar ve onaylanana kadar AKTS hesabına girmez.
  Onaylanan kayıt kilitlenir; düzeltmeyi yalnızca koordinatör gerekçe yazarak yapar.
- Aynı ders birden çok kez alınabilir; her alınış ayrı kayıttır.
- **Ders seçimi:** öğrenci içinde bulunulan dönem ("alındı") veya bir sonraki dönem ("planlandı") için
  ders listesinden seçer; serbest metinle ders giremez. Listesinde olmayan ders için koordinatöre talep
  gönderir; kabul edilirse ders listesine koordinatör tarafından eklenir.
- **Belgeler:** yalnızca PDF, JPG, PNG; en fazla 5 MB. Tür, dosya adına değil içeriğine bakılarak belirlenir.
  Dosyalar `korumali_dosyalar/` klasöründe (web kökü dışında, git'e girmez) rastgele adla saklanır ve yalnızca
  yetki kontrolüyle açılır. Belge silinmez; yeni sürüm yüklenince eskisi kalır.
- Yönerge eşikleri (GANO, AKTS, süre) koda gömülü değildir; **sürümlü kural ayarlarından** gelir.

## Proje yapısı

```
config/                 Django ayarları ve ana URL'ler
hesaplar/               Kullanıcı modeli (rol alanı) ve rol_gerekli yetki dekoratörü
takip/
  models.py             Ders, protokol, öğrenci, ders denemesi, kural ayarı, işlem kaydı
  services.py           Veriyi değiştiren TÜM işlemler buradan geçer ve işlem kaydına yazılır
  views.py              Ekranlar (yalnızca servis katmanını çağırır)
  management/commands/  seed_demo komutu
  tests/                Testler
templates/              Ortak şablonlar (base.html, giriş, 403)
```

## Durum

İlk sürüm (Ekim 2026): giriş ve roller, öğrenci ekleme, ders kataloğu, öğrenci ders listesi ve AKTS
özeti, işlem geçmişi, demo verisi. Sonra eklenenler: onay / ret ekranı, öğrencinin ders seçimi ve ders talepleri, belge yükleme ve inceleme.

Henüz yapılmayanlar:

- Öğrencinin dönem sonu notlarını girmesi (transkript yüklenmeden onaya gönderilemeyecek)
- Koordinatör ↔ öğrenci mesajlaşma
- Kural ayarlarına göre uyarı üretme (GANO, ders almama, süre)

## Sorun giderme

- **"You have unapplied migration(s)" uyarısı** (ör. yeni bir sürümü çektikten sonra): `.\.venv\Scripts\python.exe manage.py migrate` çalıştırın.
- **Giriş kilitlendi:** şifre 5 kez yanlış girilince hesap 30 dakika kilitlenir. Hemen açmak için:
  `.\.venv\Scripts\python.exe manage.py axes_reset`
- **Temiz başlamak:** sunucuyu durdurun, `db.sqlite3` dosyasını ve `korumali_dosyalar` klasörünü silin, ardından `migrate` ve `seed_demo`
  komutlarını yeniden çalıştırın.
