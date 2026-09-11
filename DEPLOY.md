# Dard.uz — Deploy runbook

> Bu hujjat **tinch paytda** yozilgan, chunki kerak bo'lganda yozishga
> vaqt bo'lmaydi. Har bir buyruq nusxa olib ishlatiladigan holatda.

**Joriy bosqich:** domen hali olinmagan → **IP orqali, HTTPS'siz**.
TLS qo'shish — 6-bo'lim.

---

## 1. Nima kerak

| | |
|---|---|
| Droplet | Ubuntu 24.04 LTS, **2 vCPU / 4 GB** (Basic Regular yetarli) |
| Region | Frankfurt (`fra1`) yoki Amsterdam (`ams3`) — O'zbekistonga eng yaqin |
| SSH kalit | droplet yaratishda qo'shiladi (parol EMAS) |

**Nega 4 GB:** Postgres + Redis + Gunicorn (3 worker) + Celery worker + beat
+ nginx. 2 GB da xotira cho'qqisida OOM-killer jarayonni o'ldiradi va sayt
sababsiz "yiqiladi". Bootstrap skripti qo'shimcha 2 GB swap ham qo'shadi.

### SSH kalit yaratish (lokal mashinada)

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\dard_deploy -C "dard-deploy"
```

⚠️ Parol so'ralganda **bo'sh qoldiring** — GitHub Actions parolli kalitni
ocha olmaydi.

Ochiq kalit (`dard_deploy.pub`) mazmunini droplet yaratishda "SSH Keys"
bo'limiga joylashtiring.

---

## 2. Serverni tayyorlash (bir marta)

```bash
# Lokal mashinadan:
scp -i ~/.ssh/dard_deploy scripts/server_bootstrap.sh root@<IP>:/tmp/
ssh -i ~/.ssh/dard_deploy root@<IP> "bash /tmp/server_bootstrap.sh"
```

Skript: tizim yangilanishi → `dard` foydalanuvchisi → Docker → 2 GB swap →
ufw (22/80/443) → fail2ban → SSH parol kirishini o'chirish.

### ⚠️ Skript tugagach, TERMINALNI YOPMASDAN tekshiring

```bash
ssh -i ~/.ssh/dard_deploy dard@<IP> "docker --version"
```

Ishlamasa — ochiq turgan root terminali orqali tuzating. Parol kirishi
o'chirilgan, ya'ni kalit ishlamasa serverga faqat DigitalOcean veb-konsoli
orqali kirish mumkin bo'ladi.

### Fayllarni joylashtirish

```bash
scp -i ~/.ssh/dard_deploy \
    deploy/docker-compose.server.yml \
    docker/nginx.conf \
    dard@<IP>:/opt/dard/

scp -i ~/.ssh/dard_deploy deploy/env.server.example dard@<IP>:/opt/dard/.env
ssh -i ~/.ssh/dard_deploy dard@<IP> "chmod 600 /opt/dard/.env"
```

### `.env` ni to'ldirish

```bash
ssh -i ~/.ssh/dard_deploy dard@<IP>
nano /opt/dard/.env
```

Majburiy qiymatlar:

```bash
# Lokal mashinada yarating:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
DJANGO_SECRET_KEY=<64 belgili tasodifiy>

DJANGO_ALLOWED_HOSTS=<DROPLET IP>
DJANGO_HTTPS=0                    # ⚠️ domen olinmaguncha
DJANGO_ADMIN_URL=<taxmin qilib bo'lmaydigan so'z>
POSTGRES_PASSWORD=<kuchli parol>
DARD_IMAGE=ghcr.io/<egangiz>/dard:latest
```

⚠️ **`DJANGO_HTTPS=0` — vaqtinchalik.** U bir vaqtda `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` va HSTS ni o'chiradi.
Uchtasi bir kalitdan boshqariladi, chunki yarim holat eng yomoni:
TLS'siz serverda `SESSION_COOKIE_SECURE=True` qolsa, brauzer cookie'ni
umuman yubormaydi va **admin paneliga kira olmaysiz** — xato esa "login
noto'g'ri" bo'lib ko'rinadi.

---

## 3. GitHub sozlamalari

### Repozitoriy

```bash
git remote add origin git@github.com:<egangiz>/dard.git
git push -u origin main
```

### Secrets (`Settings → Secrets and variables → Actions`)

| Nom | Qiymat |
|---|---|
| `SSH_PRIVATE_KEY` | `~/.ssh/dard_deploy` faylining **to'liq** mazmuni (`-----BEGIN` dan `-----END` gacha) |
| `SSH_KNOWN_HOSTS` | `ssh-keyscan -t ed25519 <IP>` natijasi |
| `SSH_HOST` | droplet IP |
| `SSH_USER` | `dard` |

⚠️ `SSH_KNOWN_HOSTS` **ixtiyoriy emas.** Usiz `StrictHostKeyChecking=no`
kerak bo'lardi, ya'ni DNS yoki tarmoq buzilganda SSH kaliti begona
serverga yuborilardi.

### Branch himoyasi

`.github/BRANCH_PROTECTION.md` — faqat **`CI holati`** tekshiruvini tanlang.

### GHCR paketi

Birinchi deploy'dan keyin `Packages → dard → Package settings` da paket
**private** bo'lib qoladi — bu to'g'ri. Deploy ilovasi `GITHUB_TOKEN`
bilan kiradi.

---

## 4. Birinchi deploy

```bash
git push origin main
```

Ketma-ketlik: **CI** (sifat + testlar + obraz → GHCR) → yashil bo'lsa
**Deploy** (SSH → pull → up → sog'liq tekshiruvi).

⚠️ Deploy CI yiqilsa **ishga tushmaydi**, ya'ni sinovdan o'tmagan kod
serverga chiqmaydi.

### Tekshirish

```
http://<IP>/health/          -> ok
http://<IP>/                 -> lenta
http://<IP>/<ADMIN_URL>/     -> admin
```

### Superuser

```bash
ssh dard@<IP>
cd /opt/dard
docker compose -f docker-compose.server.yml exec web python manage.py createsuperuser
```

---

## 5. Kundalik amallar

```bash
cd /opt/dard
C="docker compose -f docker-compose.server.yml"

$C ps                         # holat
$C logs -f web                # loglar
$C logs --tail=100 celery-worker
$C restart web
$C exec web python manage.py shell
$C exec db psql -U dard -d dard
```

### Orqaga qaytarish

**Variant 1 — GitHub'dan (tavsiya):**
`Actions → Deploy → Run workflow` → `image_tag` ga eski commit SHA
(12 belgi) → Run.

**Variant 2 — serverdan:**

```bash
cd /opt/dard
cat .env.oldingi_obraz              # oldingi obraz shu yerda saqlangan
grep -v '^DARD_IMAGE=' .env > .env.yangi
cat .env.oldingi_obraz >> .env.yangi
mv .env.yangi .env && chmod 600 .env
docker compose -f docker-compose.server.yml up -d
```

⚠️ **Migratsiya orqaga qaytmaydi.** Yangi versiya bazani o'zgartirgan
bo'lsa, eski kod u bilan ishlamasligi mumkin. Xavfli migratsiyalardan
oldin zaxira oling (7-bo'lim).

---

## 6. TLS qo'shish (domen olingandan keyin)

### 6.1 DNS

| Turi | Nom | Qiymat |
|---|---|---|
| A | `@` | `<IP>` |
| A | `www` | `<IP>` |

Tarqalishini kuting: `nslookup dard.uz`

### 6.2 Sertifikat

```bash
ssh dard@<IP>
cd /opt/dard
mkdir -p certbot/www certbot/conf

docker run --rm \
  -v /opt/dard/certbot/www:/var/www/certbot \
  -v /opt/dard/certbot/conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d dard.uz -d www.dard.uz \
  --email <email> --agree-tos --no-eff-email
```

⚠️ Bundan oldin `nginx.conf` ga `/.well-known/acme-challenge/` yo'lini
qo'shing, aks holda tekshiruv o'tmaydi.

### 6.3 Yoqish

1. `nginx.conf` ga 443 bloki + sertifikat yo'llari
2. `docker-compose.server.yml` da `443:443` va certbot volume'larini oching
3. `.env`:
   ```bash
   DJANGO_HTTPS=1
   DJANGO_ALLOWED_HOSTS=dard.uz,www.dard.uz
   DJANGO_HSTS_SECONDS=3600     # ⚠️ kichikdan boshlang
   ```
4. `docker compose -f docker-compose.server.yml up -d`

⚠️ **HSTS'ni darhol 1 yilga qo'ymang.** Sertifikatda muammo chiqsa,
brauzerlar domenni oylar davomida HTTPS'siz ochmaydi. Bir necha kun
`3600` bilan ishlating, keyin oshiring.

### 6.4 Avtomatik yangilash

```bash
crontab -e
```

```cron
0 3 * * 1 cd /opt/dard && docker run --rm -v /opt/dard/certbot/www:/var/www/certbot -v /opt/dard/certbot/conf:/etc/letsencrypt certbot/certbot renew --quiet && docker compose -f docker-compose.server.yml exec -T nginx nginx -s reload
```

---

## 7. Zaxira (D7-T3 da to'liq avtomatlashtiriladi)

```bash
cd /opt/dard
docker compose -f docker-compose.server.yml exec -T db \
  pg_dump -U dard dard | gzip > backups/dard-$(date +%F-%H%M).sql.gz
```

Tiklash:

```bash
gunzip -c backups/<fayl>.sql.gz | \
  docker compose -f docker-compose.server.yml exec -T db psql -U dard -d dard
```

⚠️ **Sinalmagan zaxira — zaxira emas, umid.** Tiklashni kamida bir marta
haqiqatan bajaring va qancha vaqt olishini o'lchang.

⚠️ Zaxira **serverning o'zida** turibdi. Server yo'qolsa u ham yo'qoladi —
D7-T3 da tashqi saqlashga ko'chiriladi.

---

## 8. Nosozliklar

### Sayt ochilmaydi

```bash
cd /opt/dard && docker compose -f docker-compose.server.yml ps
```

| Holat | Sabab |
|---|---|
| `web` — `Restarting` | sozlama xatosi. `logs web` ga qarang: ko'pincha `.env` da majburiy qiymat bo'sh |
| `db` — `unhealthy` | disk to'lgan (`df -h`) yoki parol o'zgartirilgan |
| hammasi `Up`, sayt yo'q | ufw: `sudo ufw status` da 80 ochiqmi |

### Admin paneliga kira olmayapman

⚠️ Eng ko'p uchraydigan sabab: `.env` da `DJANGO_HTTPS=1`, lekin TLS yo'q.
Cookie `Secure` bayrog'i bilan yuborilib, brauzer uni qaytarmaydi. Login
formasi "noto'g'ri" deydi, aslida parol to'g'ri.

```bash
grep DJANGO_HTTPS /opt/dard/.env    # TLS yo'q bo'lsa 0 bo'lishi kerak
```

### Cheksiz qayta yo'naltirish

Xuddi shu sabab: `SECURE_SSL_REDIRECT` yoqilgan, nginx'da TLS yo'q.

### Deploy sog'liq tekshiruvida yiqildi

```bash
docker compose -f docker-compose.server.yml logs --tail=100 web
```

Ko'pincha migratsiya xatosi. Baza holati noaniq bo'lsa — zaxiradan tiklang,
keyin qayta deploy qiling.

### Qidiruv hech narsa topmayapti

⚠️ Qidiruv buzilganda **xato chiqmaydi** — natija shunchaki bo'sh bo'ladi.
Uch ehtimol, shu tartibda tekshiring:

```bash
# 1. Indeks ustunlari haqiqatan to'ldirilganmi
docker compose -f docker-compose.server.yml exec web     python manage.py qidiruvni_yangilash --tekshir
```

| Natija | Ma'nosi |
|---|---|
| `0 tasi eskirgan` | indeks joyida — muammo boshqa yerda |
| `N tasi eskirgan` | `--tekshir` siz qayta ishga tushiring |

⚠️ Normallashtirish qoidalari o'zgarganda qayta indekslash **migratsiya
bilan** keladi (`0006_qidiruv_transliteratsiya` namunasi) va `entrypoint`
da avtomatik bajariladi — bu buyruq faqat ta'mirlash uchun.

2. **`pg_trgm` kengaytmasi.** `0005_qidiruv_indeksi` migratsiyasi
   `CREATE EXTENSION` bajaradi va bu **superuser** huquqini talab qiladi.
   O'z Postgres konteynerimizda muammo yo'q, lekin boshqariladigan bazaga
   (DigitalOcean, Neon, Supabase) ko'chilganda migratsiya ruxsat xatosi
   bilan yiqiladi — kengaytmani panel orqali bir marta yoqing.

```bash
docker compose -f docker-compose.server.yml exec db     psql -U dard -d dard -c "SELECT extname FROM pg_extension;"
```

3. **Ommaviy kiritilgan kontent.** `bulk_create` / `bulk_update` `save()` ni
   chetlab o'tadi. Model menejeri buni yopadi, lekin xom SQL bilan
   yozilgan qatorlar indeksdan tashqarida qoladi — `qidiruvni_yangilash`
   ularni tuzatadi.

### Google saytni ko'rmayapti

```bash
curl -s https://dard.uz/robots.txt
curl -s https://dard.uz/sitemap.xml | head -5
```

Domen olingandan keyin **bir marta**: Search Console'da domen
tasdiqlanadi va `https://dard.uz/sitemap.xml` yuboriladi.

⚠️ Sitemap `Sitemap:` qatori orqali `robots.txt` da ham e'lon qilinadi,
lekin Search Console'ga qo'lda yuborish indekslashni tezlashtiradi va
xatolarni ko'rsatadi.

⚠️ `sitemap.xml` **faqat ko'rinadigan** kontentni beradi. Yashirilgan
post u yerda paydo bo'lsa — bu jiddiy nosozlik, `visible()` biror
joyda unutilgan degani.

### Ijtimoiy tarmoqda karta rasmsiz chiqyapti

OG rasmlarini **Celery worker** yozadi va ular `media_data` volumeda
turadi (`web`, `celery-worker` va nginx uchalasiga ham ulangan).

```bash
# Rasmlar bormi
docker compose -f docker-compose.server.yml exec web ls -la /app/media/og | head

# Yo'q bo'lsa — yasab chiqing
docker compose -f docker-compose.server.yml exec web \
    python manage.py og_rasmlarni_yangilash --faqat-yoqlar
```

⚠️ **Brend yoki maket o'zgarganda** eski kartalar eski ko'rinishda
qolib ketadi va ular ijtimoiy tarmoqda yillab aylanib yuradi:

```bash
docker compose -f docker-compose.server.yml exec web python manage.py og_standart
docker compose -f docker-compose.server.yml exec web python manage.py og_rasmlarni_yangilash
```

⚠️ Telegram va Facebook `og:image` ni **manzil bo'yicha** keshlaydi.
Fayl nomida mazmun hashi bo'lgani uchun yangi rasm yangi manzilga
tushadi — lekin ALLAQACHON ulashilgan havolalar eski kartani
ko'rsatishda davom etadi (buni faqat platformaning o'z vositasi
yangilaydi).

### Disk to'ldi

```bash
df -h
docker system df
docker image prune -a -f --filter "until=168h"
docker volume ls          # ⚠️ volume'larni O'CHIRMANG — ma'lumot yo'qoladi
```

### Xotira tugadi (OOM)

```bash
free -h
dmesg | grep -i "killed process"
```

Swap ishlayotganini tekshiring. Takrorlansa Gunicorn worker sonini
kamaytiring (`--workers=2`) yoki droplet'ni kattalashtiring.

---

## 9. To'lov tizimlari (Click, Payme) — D6-T2, D6-T3

⚠️ **Kalitlarsiz hech kimdan pul olinmaydi.** `CLICK_MERCHANT_ID`,
`CLICK_SERVICE_ID`, `CLICK_SECRET_KEY` — uchalasi ham to'ldirilmaguncha
`/pro/` sahifasida «To'lash» tugmasi **ko'rsatilmaydi**. Ya'ni kodni
prodga chiqarish xavfsiz; to'lov faqat ongli qadamdan keyin yoqiladi.

### 9.1 Click merchant kabinetida

Ikkita manzil kiritiladi (`https://` bilan, oxiridagi `/` **shart**):

| Maydon | Qiymat |
|---|---|
| Prepare URL | `https://<domen>/tolov/click/prepare/` |
| Complete URL | `https://<domen>/tolov/click/complete/` |

⚠️ Manzil keyin o'zgarsa to'lovlar **jimgina** to'xtaydi: sayt ishlaydi,
tugma ishlaydi, faqat obuna berilmaydi. Shuning uchun bu manzillar kodda
qotirilgan va muhitdan olinmaydi.

### 9.2 `.env`

```bash
CLICK_MERCHANT_ID=...      # kabinetdan
CLICK_SERVICE_ID=...       # kabinetdan (xizmat, merchant EMAS)
CLICK_SECRET_KEY=...       # kabinetdan
OBUNA_NARXI=19000          # so'm / OBUNA_MUDDATI_KUN kun
# Sandbox'da boshqa manzil beriladi:
CLICK_TOLOV_MANZILI=https://my.click.uz/services/pay
```

⚠️ `ISHONCHLI_PROKSILAR_SONI=1` bo'lishini tekshiring (nginx ortida).
Aks holda to'lov jurnalidagi IP har doim nginx'niki bo'ladi va nizoda
so'rov qayerdan kelganini aytib bo'lmaydi.

### 9.3 Tekshirish

```bash
# 1. Migratsiya qo'llanganmi
docker compose -f docker-compose.prod.yml exec web   python manage.py showmigrations payments

# 2. Webhook tashqaridan ochiqmi (imzosiz so'rov -1 qaytarishi KERAK)
curl -s -X POST https://<domen>/tolov/click/prepare/ -d "action=0"
# Kutilgan: {"...","error":-1,"error_note":"SIGN CHECK FAILED!"}
# ⚠️ HTTP holati 200 bo'lishi SHART. 4xx/5xx Click uchun "javob yo'q"
#    degani va u tranzaksiyani bekor qiladi.

# 3. Jurnal to'lyaptimi (har so'rov yoziladi, imzosizlari ham)
docker compose -f docker-compose.prod.yml exec web   python manage.py shell -c   "from apps.payments.models import TolovSorovi; print(TolovSorovi.objects.count())"
```

### 9.4 Payme (D6-T3)

Payme'da **bitta** manzil ko'rsatiladi — oltita metod ham shu yerga
JSON-RPC bo'lib keladi:

| Maydon | Qiymat |
|---|---|
| Endpoint URL | `https://<domen>/tolov/payme/` |
| `account` maydoni | **`order_id`** |

⚠️ `account` maydonining nomi kabinetda **aynan `order_id`** bo'lishi
shart (`apps/payments/payme.py::ACCOUNT_MAYDONI`). Mos kelmasa har
so'rov «buyurtma topilmadi» bilan qaytadi va sabab hech qayerda
ko'rinmaydi — Payme foydalanuvchiga faqat umumiy xabar ko'rsatadi.

```bash
PAYME_MERCHANT_ID=...            # kabinetdagi kassa ID
PAYME_SECRET_KEY=...             # Merchant API Basic-auth paroli
PAYME_CHECKOUT_MANZILI=https://checkout.paycom.uz
```

⚠️⚠️ **Sandbox va prod kalitlari BOSHQA.** Sandbox kalitini prodga
olib o'tish hamma so'rovni `-32504` («huquq yetarli emas») bilan rad
ettiradi — sayt ishlaydi, to'lov esa umuman o'tmaydi.

Tekshirish (avtorizatsiyasiz so'rov `-32504` qaytarishi KERAK):

```bash
curl -s -X POST https://<domen>/tolov/payme/   -H 'Content-Type: application/json'   -d '{"jsonrpc":"2.0","id":1,"method":"CheckPerformTransaction","params":{}}'
# Kutilgan: {"...","error":{"code":-32504,...}}
# ⚠️ HTTP holati 200 bo'lishi SHART (Click bilan bir xil sabab).
```

Sandbox (`test.paycom.uz`) ikkita ssenariyni yurgizadi: tasdiqlanmagan
tranzaksiya (yaratish -> bekor) va tasdiqlangan tranzaksiya
(yaratish -> bajarish -> bekor). Ikkalasi ham
`apps/payments/tests_payme.py` da takrorlangan.

⚠️ **Pul qaytarilsa obuna kunlari ham qaytarib olinadi.** Payme
kabinetidan tranzaksiya bekor qilinsa (`state = -2`), `berilgan_kun`
obunadan ayiriladi. Bu ONGLI qaror: aks holda «to'la -> PRO ol ->
pulni qaytar -> PRO qolsin» yo'li ochiq qolardi.

---

### 9.5 Nizo bo'lsa («pul yechildi, obuna yo'q»)

Admin -> **To'lov so'rovlari jurnali** (`/…/payments/tolovsorovi/`).
Buyurtma raqami yoki `click_trans_id` bo'yicha qidiring. Jurnal
**o'zgarmas**: har so'rov, kelgan ma'lumot va bizning javobimiz turadi.
Imzoning o'zi ataylab saqlanmaydi (maxfiy kalit ishtirokidagi hash).

Obunani qo'lda berish: Admin -> **Obunalar** (`Tolov` emas — u faqat
o'qish uchun, chunki u haqiqiy pul harakati yozuvi).

### 9.6 Postni ko'tarish (boost) — D6-T4

Yangi webhook manzili **YO'Q**: boost Click/Payme'ning o'sha manzillari
orqali to'lanadi (`TolovMaqsadi.BOOST`). Kerak bo'lgani — narx:

```bash
BOOST_NARXI=5000           # so'm / BOOST_MUDDATI_KUN kun (standart 1)
```

⚠️ **Sotuv cheklanmagan** (foydalanuvchi qarori, 2026-09-11):
«Qaynoq»ning birinchi sahifasida 4 ta joy bor (3, 8, 13, 18-o'rinlar) va
faol boost ko'p bo'lsa joylar navbat bilan bo'linadi. Sotib olish
sahifasi hozir nechta post ko'tarilganini ochiq yozadi. Talab oshsa
birinchi qadam — narxni oshirish (`BOOST_NARXI`), kodga tegish shart
emas.

⚠️ **Pul avtomatik qaytarilmaydigan holatlar.** To'lovdan OLDIN
(Prepare / CreateTransaction) post yashirilgan, o'chirilgan, yechilgan
yoki muallif cheklangan bo'lsa — provayderga xato ketadi va pul
YECHILMAYDI. To'lovdan KEYIN esa:
- post yashirilsa yoki o'chirilsa — boost lentada chiqmaydi, to'lov
  esa bo'lgan;
- Prepare bilan Complete orasidagi soniyalarda post yechilsa.

Bu holatlarda pulni qaytarish qarori odamniki (Payme kabinetidan
bekor qilish yoki qo'lda). Admin -> **Ko'tarishlar** faqat o'qish
uchun: qo'lda «ko'tarib qo'yish» pulsiz pullik joy bo'lardi.

⚠️ Payme'dan pul qaytarilsa (`state = -2`) o'sha to'lovning ko'tarish
oralig'i darhol yopiladi (navbatdagisi — nol uzunlikka tushadi).

---

## 10. Hali qilinmagan

| Nima | Faza |
|---|---|
| TLS / HTTPS | domen olingach (6-bo'lim) |
| Tashqi zaxira + tiklash mashqi | D7-T3 |
| Sentry (xatolar) | D7-T1 |
| Tashqi uptime monitoring | D7-T2 |
| Yuk testi | D7-T5 |
