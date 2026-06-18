# Weather Decision Agent

Weather Decision Agent, hava durumu ve kullanıcı tercihlerini analiz ederek
uygun aktivite önerileri üretmeyi amaçlayan bir Agentic AI projesidir.

## Mevcut Kabiliyetler

- Open-Meteo üzerinden güncel hava durumu ve yedi günlük tahmin verisi alır.
- Kullanıcının şehir, tarih, aktivite ve konfor tercihlerini değerlendirir.
- Aktivite kataloğunu deterministik güvenlik kurallarından geçirir.
- Önce tam eşleşmeleri, ardından yakın kapalı alan alternatiflerini dener.
- Hava koşullarından `LOW`, `MODERATE`, `HIGH`, `SEVERE` risk seviyesi üretir.
- Önerileri hava güvenliği, tercih eşleşmesi, konfor ve pratiklik kırılımıyla
  puanlar.
- Güvenli bir sonuç bulunamazsa kontrollü şekilde durur.
- Katalog güvenli sonuç bulamazsa LLM'den kontrollü aktivite adayları alabilir;
  bu adaylar da aynı deterministik güvenlik kurallarından geçmeden önerilmez.
- Opsiyonel OpenAI entegrasyonu ile sonucu açıklar ve ikinci hakem görüşü üretir.
- Streamlit arayüzü üzerinden öneri akışını çalıştırır.
- Streamlit'te User Mode ile sade öneri akışı, Developer Mode ile evaluator,
  trace, raw hava verisi ve score breakdown detayları gösterir.
- Reproducible evaluation senaryolarıyla exact match, fallback ve güvenli durma
  davranışlarını test eder.
- Opsiyonel JSONL history repository ile öneri geçmişi ve kullanıcı feedback'i
  saklar; Streamlit üzerinden beğendim/beğenmedim geri bildirimi alınabilir.

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

- geçmiş ekranını kullanıcı/geliştirici mod ayrımına göre düzenlemek

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
