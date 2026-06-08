# Weather Decision Agent

Weather Decision Agent, hava durumu ve kullanıcı tercihlerini analiz ederek
uygun aktivite önerileri üretmeyi amaçlayan bir Agentic AI projesidir.

## Proje Yapısı

- `app/`: Uygulamanın Python kodları
- `data/`: Projede kullanılacak örnek ve değerlendirme verileri
- `tests/`: Otomatik testler
- `evaluation/`: Agent sonuçlarını değerlendiren sistem
- `docs/`: Mimari, blog ve proje notları

## Durum

Projenin temiz başlangıç yapısı oluşturuldu.

İlk domain modelleri eklendi:

- `WeatherData`: Normalize edilmiş hava durumu bilgisi
- `UserPreferences`: Kullanıcı tercihleri ve sınırları
- `Activity`: Önerilebilecek aktivite adayı
- `Recommendation`: Agent tarafından üretilecek öneri çıktısı
