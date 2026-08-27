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

## 9. Hali qilinmagan

| Nima | Faza |
|---|---|
| TLS / HTTPS | domen olingach (6-bo'lim) |
| Tashqi zaxira + tiklash mashqi | D7-T3 |
| Sentry (xatolar) | D7-T1 |
| Tashqi uptime monitoring | D7-T2 |
| Yuk testi | D7-T5 |
