# Supervisor Workflow (Phase C)
**Ajan Koordinasyonu & Hafıza Yönetimi İş Akışı**

Bu iş akışı, hedefin sınırlarının geniş olduğu (Bug Bounty, Internal Pentest vb.) ve tek bir Claude oturumunun / context'inin tüm bilgileri tutmakta zorlanacağı durumlarda **Takım Lideri (Supervisor)** rolü üstlendiğinde uygulanmalıdır.

## Temel Kurallar
1. Tüm keşif çıktılarını `memory-server`'a yaz. Yüzlerce satır logu context'e alma!
2. Delta Scanner Daemon'u (recon_daemon.py) arkaplanda çalıştırıp değişiklikleri bekle.
3. Bulunan zafiyet tiplerine göre yetkin "Skill" leri yükle ve alt-odaklı analiz yap.

## Faz 1: Hafıza Taraması (Memory Recon)
Göreve başlarken hedefe daha önce saldırılıp saldırılmadığını kontrol et.
- [ ] `get_target_memory("hedef.com")` çalıştır.
- [ ] Daha önceden bulunmuş açık portlar, directory'ler var mı?
- [ ] Varsa doğrudan **Faz 3**'e geç. Yoksa Recon'u başlat.

## Faz 2: Merkezi Keşif (Central Recon)
- [ ] Hedefte `nmap_scan` / `ffuf_fuzz` / `subfinder_enum` komutlarını çalıştır.
- [ ] Çıktıdaki her yeni endpoint'i, subdomain'i tek tek **`store_endpoint`** ile hafızaya kaydet.
- [ ] Eğer bir paralo/hash bulunursa **`store_credential`** ile hafızaya kaydet.
- [ ] Uzun işlemler için `recon_daemon.py` servisini (daemon) başlat (bkz. Phase C Daemon) ve arkaplana at.

## Faz 3: Dağıtımlı Saldırı (Distributed Exploit)
Bu fazda spesifik zafiyetlere odaklanın;
- [ ] Eğer hafızada web form / URL parametresi var ise → `web-exploit` skill kurallarını işlet.
- [ ] Eğer SQL injection / kör enjeksiyon tespiti varsa → `sqlmap_test` ile veriyi dump et.
- [ ] Eğer binary servis var ise → `binary-pwn` odaklı çalış.
- [ ] Sonuç **Başarılı (Exploited)** ise -> Zafiyeti detaylıca `store_finding` aracı ile hafızaya kaydet. Tüm payload'ları belirt.

## Faz 4: Consolidation (Birleştirme & Raporlama)
- [ ] Tarama süreci bittiğinde `get_target_memory("hedef")` çağırarak ne elde edildiğine bak.
- [ ] Tüm zafiyetler (findings) üzerinden CVSS hesaplayıp HackerOne formatında raporu üret.
- [ ] (Opsiyonel) Eğer kullanıcı dilerse `drop_target_memory` kullanarak hafızayı temizle.
