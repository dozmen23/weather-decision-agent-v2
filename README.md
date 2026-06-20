# Weather Decision Agent

Weather Decision Agent, hava durumu ve kullanıcı tercihlerini analiz ederek
uygun aktivite önerileri üretmeyi amaçlayan bir Agentic AI projesidir.

## Mevcut Kabiliyetler

- Open-Meteo üzerinden güncel hava durumu ve yedi günlük tahmin verisi alır.
- Şehir adı veya doğrudan koordinat üzerinden hava verisi alabilecek servis
  altyapısına sahiptir.
- Streamlit'te şehir ya da harita modu seçilebilir; harita modunda kullanıcı
  OpenStreetMap üzerinden bir noktaya tıklayıp aynı öneri akışını çalıştırır.
- Kullanıcının şehir, tarih, aktivite ve konfor tercihlerini değerlendirir.
- Bütçe, süre, yoğunluk ve rezervasyon istemiyorum tercihlerini filtre olarak
  uygular.
- Katılımcı tercihini tek başıma, arkadaşla veya aileyle şeklinde dikkate alır.
- Ulaşım kolaylığı tercihini aktivite düzeyinde dikkate alır; bu alan ileride
  harita veya gerçek mekan verisiyle beslenebilir.
- Kontrollü demo mekan veri kaynağından doğrulanmış mekan adayları gösterebilir;
  haritada seçilen noktaya göre mekan mesafelerini yeniden hesaplar ve adayları
  haritada marker olarak gösterebilir.
- Developer Mode'da mekan filtre izini gösterir; hangi mekanın hangi nedenle
  elendiği veya geçtiği görülebilir.
- Mekan kaynağı provider mimarisiyle ayrılmıştır; JSON demo provider, static
  test provider, generic external provider ve Google Places provider sınırı
  vardır.
- `VENUE_PROVIDER=json`, `VENUE_PROVIDER=google_places` ve opsiyonel
  `VENUE_JSON_PATH` ayarlarıyla mekan kaynağı merkezi olarak seçilebilir.
- Google Places modunda Nearby Search, haritada seçilen koordinata göre çalışır;
  API key `.env` içindeki `GOOGLE_PLACES_API_KEY` üzerinden okunur.
- Hava ve pratiklik filtrelerini teknik sayı girişi yerine doğal seviye
  seçenekleriyle toplar.
- Yedi günlük tahmini kartlı gün seçiciyle gösterir.
- Aktivite kataloğunu deterministik güvenlik kurallarından geçirir.
- Önce tam eşleşmeleri, ardından yakın kapalı alan alternatiflerini dener.
- Kritik kategorilerde açık alan ve kapalı alan alternatiflerinin birlikte
  kalmasını otomatik testlerle güvenceye alır.
- Hava koşullarından `LOW`, `MODERATE`, `HIGH`, `SEVERE` risk seviyesi üretir.
- Önerileri hava güvenliği, tercih eşleşmesi, konfor ve pratiklik kırılımıyla
  puanlar.
- Güvenli bir sonuç bulunamazsa kontrollü şekilde durur.
- Katalog güvenli sonuç bulamazsa LLM'den kontrollü aktivite adayları alabilir;
  bu adaylar da aynı deterministik güvenlik kurallarından geçmeden önerilmez.
- LLM alakasız aktivite üretirse, öneri açıklamasında aday uydurursa veya
  geçersiz sonucu onaylamaya çalışırsa testlerle reddedilir.
- Opsiyonel OpenAI entegrasyonu ile sonucu açıklar ve ikinci hakem görüşü üretir.
- Streamlit arayüzü üzerinden öneri akışını çalıştırır.
- Streamlit'te User Mode ile sade öneri akışı, Developer Mode ile evaluator,
  trace, raw hava verisi ve score breakdown detayları gösterir.
- User Mode öneri kartlarında "Neden bunu önerdim?" ve "Dikkat et" bölümleri
  kullanıcı diliyle gösterilir.
- Fallback açıklamaları yağış, rüzgâr, sıcaklık ve risk sınırlarını
  kullanıcı diliyle belirtir.
- Geçmiş ekranı User Mode'da sade öneri geçmişi, Developer Mode'da raw kayıt
  ve debug bilgileri olarak ayrılır.
- Developer Mode'da evaluation dashboard üzerinden kayıtlı senaryolar
  çalıştırılıp pass/fail sonuçları görülebilir.
- Katalogdaki aktivite adları ve aktivite türleri User Mode'da Türkçe
  etiketlerle gösterilir.
- Reproducible evaluation senaryolarıyla exact match, fallback, güvenli durma,
  coordinate-origin venue sorting ve venue filtering trace davranışlarını test
  eder.
- Opsiyonel JSONL history repository ile öneri geçmişi ve kullanıcı feedback'i
  saklar; Streamlit üzerinden beğendim/beğenmedim geri bildirimi alınabilir.
- Feedback geçmişinden küçük kişiselleştirme sinyali üretir; kapalı alan
  önerileri net olumsuzlanırsa kapalı seçeneklere düşük bir skor cezası verir.

## Proje Yapısı

- `app/`: Uygulamanın Python kodları
- `data/`: Aktivite, demo mekan ve değerlendirme verileri
- `tests/`: Otomatik testler
- `evaluation/`: Agent sonuçlarını değerlendiren sistem
- `docs/`: Mimari, blog ve proje notları

## Durum

Proje, çalışan bir deterministik öneri akışına sahiptir. Ana karar mekanizması
LLM'e bırakılmaz; LLM yalnızca açıklama, aday üretimi ve değerlendirme desteği
için kullanılır.

Temel domain modelleri:

- `WeatherData`: Normalize edilmiş hava durumu bilgisi
- `UserPreferences`: Kullanıcı tercihleri ve sınırları
- `Activity`: Önerilebilecek aktivite adayı
- `Recommendation`: Agent tarafından üretilecek öneri çıktısı

Yakın vadeli geliştirme yönü:

- harita destekli lokasyon seçimini canlı mekan verisiyle ilişkilendirmek
- demo mekan veri kaynağını ileride canlı mekan API'siyle değiştirilebilir
  hale getirmek

## Yerel Kurulum

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Gerçek LLM entegrasyonu için `.env.example` dosyasını `.env` olarak
kopyalayıp ayarları doldurun. `.env` dosyası Git tarafından takip edilmez.
Mekan önerileri varsayılan olarak kontrollü JSON demo kataloğunu kullanır;
farklı bir JSON katalog için `VENUE_JSON_PATH` ayarlanabilir.

Web arayüzünü başlatmak için:

```bash
streamlit run streamlit_app.py
```

Testleri çalıştırmak için:

```bash
pytest
```
