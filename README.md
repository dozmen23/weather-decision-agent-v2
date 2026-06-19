# Weather Decision Agent

Weather Decision Agent, hava durumu ve kullanıcı tercihlerini analiz ederek
uygun aktivite önerileri üretmeyi amaçlayan bir Agentic AI projesidir.

## Mevcut Kabiliyetler

- Open-Meteo üzerinden güncel hava durumu ve yedi günlük tahmin verisi alır.
- Kullanıcının şehir, tarih, aktivite ve konfor tercihlerini değerlendirir.
- Bütçe, süre, yoğunluk ve rezervasyon istemiyorum tercihlerini filtre olarak
  uygular.
- Katılımcı tercihini tek başıma, arkadaşla veya aileyle şeklinde dikkate alır.
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
- Reproducible evaluation senaryolarıyla exact match, fallback ve güvenli durma
  davranışlarını test eder.
- Opsiyonel JSONL history repository ile öneri geçmişi ve kullanıcı feedback'i
  saklar; Streamlit üzerinden beğendim/beğenmedim geri bildirimi alınabilir.
- Feedback geçmişinden küçük kişiselleştirme sinyali üretir; kapalı alan
  önerileri net olumsuzlanırsa kapalı seçeneklere düşük bir skor cezası verir.

## Proje Yapısı

- `app/`: Uygulamanın Python kodları
- `data/`: Projede kullanılacak örnek ve değerlendirme verileri
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

- ulaşım kolaylığı gibi kalan tercih filtrelerini eklemek

## Yerel Kurulum

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Gerçek LLM entegrasyonu için `.env.example` dosyasını `.env` olarak
kopyalayıp ayarları doldurun. `.env` dosyası Git tarafından takip edilmez.

Web arayüzünü başlatmak için:

```bash
streamlit run streamlit_app.py
```

Testleri çalıştırmak için:

```bash
pytest
```
