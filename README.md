# Dard.uz

> «Nolima, yechim topamiz» — hayotiy muammolar va real tajribaga asoslangan
> yechimlar platformasi.

- **Biznes va texnik arxitektura:** [`biznes-arxitektura-rejasi.md`](biznes-arxitektura-rejasi.md)
- **Ish rejasi:** [`def_tasks.json`](def_tasks.json) — 66 task, 8 faza
- **Dizayn tizimi:** [`frontend/design-system/MASTER.md`](frontend/design-system/MASTER.md)

**Stek:** Django 6.1 · PostgreSQL 17 · Redis 7 · Celery 5.5 · Tailwind CSS v4 · HTMX

---

## Ishga tushirish — Docker (tavsiya etiladi)

```bash
cp .env.example .env          # dev uchun tahrirlash shart emas
docker compose up -d --build
```

| Manzil | Nima |
|---|---|
| http://127.0.0.1:8001/ | Lenta (hozircha maket ma'lumoti) |
| http://127.0.0.1:8001/health/ | Tiriklik tekshiruvi |
| http://127.0.0.1:8001/admin/ | Admin panel |

```bash
docker compose logs -f web              # loglar
docker compose exec web python manage.py createsuperuser
docker compose down                     # to'xtatish (ma'lumot saqlanadi)
docker compose down -v                  # ma'lumot ham O'CHADI
```

### ⚠️ Portlar standart emas

`5432 / 6379 / 8000` **ishlatilmaydi**. Bu mashinada boshqa Docker stek'lari
shu portlarni band qilishi mumkin va o'shanda
`Bind for 0.0.0.0:5432 failed: port is already allocated` xatosi chiqadi —
u qurilish (build) xatosiga o'xshab ko'rinadi, aslida esa konteyner yaratish
bosqichida yiqiladi.

| Xizmat | Host porti | Konteyner ichida |
|---|---|---|
| PostgreSQL | `5434` | `db:5432` |
| Redis | `6381` | `redis:6379` |
| Django | `8001` | `web:8000` |

`.env` orqali o'zgartirsa bo'ladi — konteyner ichidagi portlar o'zgarmaydi.

---

## Ishga tushirish — Docker'siz (faqat Django)

PostgreSQL va Redis baribir kerak. Eng oson yo'l — ularni Docker'da, Django'ni
host'da ishlatish:

```bash
docker compose up -d db redis

python -m venv .venv
.venv\Scripts\activate                  # Windows
pip install -r requirements/dev.txt

python manage.py migrate
python manage.py runserver
```

Host'dan ulanganda `.env` dagi `POSTGRES_PORT=5434` va `REDIS_URL=...:6381`
ishlatiladi (konteyner ichidagi `5432/6379` emas).

⚠️ **Windows'da Celery worker:** `celery -A config worker --pool=solo -l info`
— standart `prefork` Windows'da ishlamaydi.

---

## Loyiha tuzilishi

```
config/          sozlamalar (base/dev/prod/test), urls, celery, wsgi/asgi
apps/            domen ilovalari
  common/        abstrakt modellar, middleware, health. Eng quyi qatlam.
  accounts/      User, Telegram login, ExpertProfile
  complaints/    Complaint, Category, Tag, Vote, SavedItem
  solutions/     Solution, qabul qilish, Match
  moderation/    Report, ModerationAction, AuditLog
  gamification/  KarmaEvent, Badge, reyting
  notifications/ Notification, Telegram dispatch
  payments/      Subscription, BoostOrder, Click/Payme
templates/
  base.html      umumiy skelet — barcha sahifalar shundan meros oladi
  components/    _header, _drawer, _bottom_nav, _complaint_card, _vote, ...
  complaints/    feed, detail, create, category_list
  accounts/      login, profile, expert_list
  pages/         landing
static/          css/app.css (QURILGAN — tahrirlamang), js/app.js
tailwind/        input.css — dizayn tizimi MANBAI
docker/          nginx.conf, entrypoint.sh
requirements/    base / dev / prod
frontend/        faqat dizayn hujjatlari (design-system/)
```

### Ilovalar orasidagi qoida

1. `common` boshqa ilovalarga **bog'lanmaydi** — u eng quyi qatlam.
2. Bog'liqlik **bir tomonlama**: `solutions` → `complaints` mumkin, teskarisi
   yo'q. Aylanma import Django'da tez paydo bo'ladi va uni keyin yechish qiyin.

---

## Front-end

```bash
npm install
npm run build      # tailwind/input.css -> static/css/app.css (minified)
npm run dev        # --watch rejimi
```

⚠️ Rang yoki o'lchamni `static/css/app.css` da o'zgartirmang — u
generatsiya qilinadi va gitignore'da. Manba: `tailwind/input.css`.

⚠️ **HTML izohlari ichiga shablon tegi yozmang.** Django `<!-- ... -->` ni
ko'rmaydi va ichidagi `{% url %}` yoki `{% if %}` ni baribir bajaradi —
sahifa `NoReverseMatch` yoki yopilmagan blok bilan buziladi. Hujjatlash
uchun `{% comment %}` ishlating. Buni guard test tekshiradi.

⚠️ **Fayllarni PowerShell `Set-Content -Encoding UTF8` bilan yozmang** — u
BOM qo'shadi. `npm` buni "not valid JSON" deb rad etadi, Django esa BOM'ni
birinchi kalitga yopishtirib yuboradi.

---

### ⚠️ Statik fayl keshi (dev)

Shablonlarda `{% static %}` emas, **`{% static_v %}`** ishlatiladi:

```django
{% load statik %}
<script src="{% static_v 'js/app.js' %}" defer></script>
```

Sabab: `runserver` statik faylga `Cache-Control` **yubormaydi**, faqat
`Last-Modified`. Sarlavhasiz brauzer evristik keshlaydi va tahrirlangan
`app.js` ni **qayta so'ramaydi** — natijada eski kod ishlaydi, kodda esa
yangisi turadi. Xato mavjud bo'lmagan joyda qidiriladi.

`{% static_v %}` dev'da manzilga fayl `mtime` ini qo'shadi
(`?v=1787864301`), prodda esa hech nima qo'shmaydi — u yerda fayllar hash
bilan nomlanadi va nginx ularni `immutable` bilan beradi.

⚠️ Middleware bilan hal qilib **bo'lmaydi**: `runserver` statik fayllarni
`StaticFilesHandler` orqali beradi, u esa middleware zanjirini butunlay
chetlab o'tadi.

### HTMX

`static/js/vendor/htmx.min.js` — **vendorlangan** (CDN emas): D2-T9 da CSP
tashqi skriptni bloklaydi, bundan tashqari CDN uzilishi ovoz berishni
o'chirib qo'yardi.

Ovoz bloki (`components/_vote.html`) — oddiy `<form>`, HTMX faqat ustiga
qo'shilgan qatlam. JavaScript yuklanmasa ovoz berish **yo'qolmaydi**,
sekinlashadi xolos (POST → 302).

## Sozlamalar

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev    # standart
DJANGO_SETTINGS_MODULE=config.settings.prod   # sirlar MAJBURIY
DJANGO_SETTINGS_MODULE=config.settings.test
```

- **dev** — hech qanday muhit o'zgaruvchisisiz ishlaydi
- **prod** — `DJANGO_SECRET_KEY` yoki `DJANGO_ALLOWED_HOSTS` bo'lmasa
  **ishga tushmaydi**. Bu ataylab: yarim sozlangan server eng yomon holat.

### Muhit o'zgaruvchilari

Barcha kalitlar izohi bilan: [`.env.example`](.env.example).
Yuklovchi va turga o'girish: `config/settings/env.py` (tashqi kutubxonasiz).

**⚠️ Ustuvorlik:** haqiqiy muhit o'zgaruvchisi `.env` fayldan **ustun** turadi.

```
muhit o'zgaruvchisi  >  .env  >  koddagi standart qiymat
```

Docker'da qiymatlarni compose beradi, ya'ni bind-mount orqali konteynerga
tushgan `.env` ularni bekor qila **olmaydi**. Bu ataylab: `.env` dagi
`POSTGRES_HOST=127.0.0.1` ustun bo'lganda konteyner ma'lumotlar bazasi
o'rniga o'zini o'ziga ulashga urinardi.

Boshqa joydagi faylni ko'rsatish: `DJANGO_ENV_FILE=/path/to/.env`

**Ma'lumotlar bazasi — ikki usul:**

```bash
# 1) Boshqariladigan baza (DigitalOcean, Neon, Supabase) — berilsa USTUN
DATABASE_URL=postgres://user:parol@host:5432/dard

# 2) Alohida o'zgaruvchilar (Docker Compose uchun qulay)
POSTGRES_DB=dard
POSTGRES_USER=dard
```

Ikkalasini bir vaqtda ishlatmang — parol ikki joyda saqlansa ular
bir-biridan uzoqlashadi.

---

## Kontent modellari uchun qoida

`Complaint` va `Solution` `ContentModel` dan meros oladi. Ikki filtr bor va
ular **boshqacha ishlaydi**:

```python
Complaint.objects.all()  # o'chirilganlar AVTOMATIK chiqib ketadi
Complaint.objects.visible()  # + moderatsiyadan o'tganlar (OMMAVIY ro'yxatlar)
Complaint.all_objects.all()  # hammasi — audit va tiklash uchun
```

- **Yumshoq o'chirish** — standart bo'yicha filtrlanadi. «O'chirilgan»
  hamma uchun yo'q degani.
- **Moderatsiya** — standart bo'yicha filtrlanmaydi. Yashirilgan postni
  muallif, moderator va audit **ko'rishi kerak**; aks holda post
  «yo'qolgan» bo'lib ko'rinadi. Shuning uchun `visible()` har bir ommaviy
  so'rovda **ochiq yoziladi** — unutilgan filtr ko'rinib tursin (D2-T3).

⚠️ Yumshoq o'chirilgan yozuv bazada qoladi, ya'ni `unique=True` maydonlari
band bo'lib turaveradi. `slug` uchun `unique=True` emas, qisman cheklov
ishlating (namuna `SoftDeleteModel` docstring'ida).

---

## Testlar

**pytest** — asosiy runner. Sozlama: `pyproject.toml`.

```bash
pytest                    # hammasi + qamrov hisoboti
pytest --create-db        # migratsiya o'zgargandan keyin
pytest -k username        # nom bo'yicha filtr
pytest apps/accounts      # bitta ilova
pytest --no-cov -x        # tez: qamrovsiz, birinchi xatoda to'xtaydi
```

⚠️ `manage.py test` ham ishlaydi, lekin u **faqat `TestCase` sinflarini**
topadi — pytest uslubidagi funksiya-testlar tashqarida qoladi. Har doim
`pytest` ishlating.

### Qoidalar

- **Yangi testlar** pytest uslubida: oddiy funksiya + fixture
  (`conftest.py` da: `user`, `other_user`, `expert`, `staff`,
  `banned_user`, `auth_client`, `staff_client`).
- **Test ma'lumoti** — fabrikalar orqali (`apps/accounts/factories.py`),
  `objects.create()` emas: testda faqat sinalayotgan maydon ko'rinib tursin.
- **Qamrov 70% dan past bo'lsa** `pytest` yiqiladi (hozir 94%).
- **Ogohlantirishlar = xato** (`filterwarnings = ["error"]`) — eskirgan
  Django API'ni yangilanishdan oldin ko'rish uchun.

### Uchta himoya avtomatik ishlaydi

1. **Noto'g'ri sozlama.** `DJANGO_SETTINGS_MODULE` muhit o'zgaruvchisi
   `pyproject.toml` dagi sozlamadan **ustun** turadi. Shu shellda avval
   `dev` eksport qilingan bo'lsa, pytest dev bilan ishlaydi va buni hech
   kim aytmaydi — email/kesh testlari yolg'ondan yiqiladi. `conftest.py`
   buni darhol va ochiq to'xtatadi.

   ```powershell
   $env:DJANGO_SETTINGS_MODULE = $null; pytest
   ```

2. **Tashqi tarmoq.** Test `api.telegram.org` yoki to'lov tizimiga
   chiqmoqchi bo'lsa `RuntimeError` beradi. Aks holda CI tarmoqqa bog'liq
   bo'lib qoladi va haqiqiy botga test xabari ketishi mumkin.

3. **`--reuse-db` yo'q.** U tez, lekin migratsiya o'zgarganda bazani
   yangilamaydi va testlar eski sxemada ishlaydi — xato "sirli" ko'rinadi.
   Tezlik kerak bo'lsa qo'lda bering, keyin `--create-db` bilan yangilang.

---

## Kod sifati

```bash
ruff check . --fix     # linter (+ xavfsizlik qoidalari)
ruff format .          # formatlovchi
mypy apps config       # tiplar
pre-commit run --all-files
```

Sozlama: `pyproject.toml` (bitta joyda) + `.pre-commit-config.yaml`.

### ⚠️ Commit qilishdan oldin venv'ni faollashtiring

```powershell
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # Linux/macOS
```

`pre-commit` `mypy` va `manage.py check` hook'larini **tizim** `python`i
bilan ishga tushiradi. Venv faol bo'lmasa ular
`ModuleNotFoundError: No module named 'django'` beradi — sabab kodda emas,
PATH'da.

### ⚠️ Commit qilishdan oldin baza ham ishlab tursin

```bash
docker compose up -d db
```

`django-check` va `django-migrations` hook'lari **ishlayotgan PostgreSQL**ni
talab qiladi (D1-T5 dan beri). Bu statik tahlilga o'xshamaydi, lekin sababi
aniq:

1. `Complaint.score_cached` — `models.GeneratedField`;
2. uning tizim tekshiruvi maqsad bazaning imkoniyatlarini so'raydi,
   PostgreSQL'da esa bu server versiyasini o'qish, ya'ni **jonli ulanish**;
3. `--database` berilmagani yordam bermaydi — Django uchun
   «belgilanmagan» = «hammasi»:
   `django/core/checks/registry.py` → `if databases is None: databases = list(connections)`.

Xato ko'rinishi chalg'ituvchi: `OperationalError: connection refused`
— model yoki migratsiya bilan aloqasi yo'qdek tuyuladi.

### Nima uchun `black` va `bandit` yo'q

- **`black` → `ruff format`.** Bu black'ning qayta amalga oshirilishi:
  natija bir xil, ~30 barobar tez. Ikkalasini birga saqlash ikki
  konfiguratsiyani sinxron tutishni talab qiladi va chekka holatlarda
  ular bir-biriga qarshi chiqadi.
- **`bandit` → ruff `S` qoidalari.** Xuddi shu tekshiruvlar (flake8-bandit),
  alohida vosita va alohida ishga tushirishsiz.

### mypy qamrovi

`strict = true` **ataylab yoqilmagan**: Django'ning dinamik tabiati sof
strict rejimda yuzlab yolg'on ogohlantirish beradi va vosita e'tiborsiz
qoldiriladigan bo'lib qoladi. Yoqilgani — `check_untyped_defs`,
`warn_unused_ignores`, `no_implicit_optional`: bular haqiqiy xatolarni
ushlaydi, shovqin qilmasdan.

Testlar va fabrikalar tekshiruvdan **chiqarilgan**: `UserFactory()` ish
vaqtida `User` qaytaradi, statik tahlilda esa `UserFactory` bo'lib
ko'rinadi (django-stubs va factory_boy o'rtasidagi ma'lum cheklov).

## CI (GitHub Actions)

`.github/workflows/ci.yml` — har push va PR'da:

| Job | Nima qiladi | Xizmatlar |
|---|---|---|
| **Sifat** | `pre-commit run --all-files` (ruff, mypy, django check, fayl gigiyenasi) | PostgreSQL 17 ⚠️ |
| **Testlar** | `pytest --create-db` + qamrov chegarasi | PostgreSQL 17, Redis 7 |
| **Docker obrazi** | prod obrazi quriladimi | — |
| **CI holati** | yig'ma natija — branch himoyasi shunga bog'lanadi | — |

Uchtasi **parallel** ishlaydi.

### Nega CI `pre-commit` ni ishlatadi

`ruff` va `mypy` ni CI'da alohida yozish mumkin edi, lekin o'shanda ular
`.pre-commit-config.yaml` dan asta-sekin **uzoqlashadi**: kimdir hookka
qoida qo'shadi, CI bilmaydi — va «lokalda o'tdi, CI'da yiqildi» (yoki
undan yomoni: teskarisi) holati paydo bo'ladi.

Bitta manba — ikki joyda bir xil natija.

### ⚠️ CI'da portlar boshqacha

Loyiha sozlamasida `POSTGRES_PORT` standarti **5434** (lokal Docker
stack'lar to'qnashmasligi uchun). GitHub Actions xizmatlari esa runner'da
`localhost:5432` da turadi — shuning uchun workflow'da ochiq beriladi.

### Branch himoyasi

CI yashil bo'lmasa merge bloklanishi uchun GitHub sozlamasi kerak —
u kodda emas: [`.github/BRANCH_PROTECTION.md`](.github/BRANCH_PROTECTION.md).

Faqat **`CI holati`** tekshiruvini tanlang, alohida job'larni emas.

## Bajarilgan ishlar

| Task | Nima |
|---|---|
| D0-T1 | Django skeleti — settings bo'linishi, `apps/` tuzilishi |
| D0-T2 | `accounts.User` — CI-noyob username, Telegram ID, blok holati |
| D0-T3 | Docker Compose — web, db, redis, celery×2, nginx (prod) |
| D0-T4 | Muhit konfiguratsiyasi — `.env` yuklovchi, `DATABASE_URL`, `.env.example` |
| D0-T5 | Abstrakt modellar — `TimeStamped`, `SoftDelete`, `Moderated`, `Content` |
| D0-T6 | Maket Django shablonlariga ko'chirildi — `base.html` + komponentlar |
| D0-T7 | pytest + factory_boy + qamrov (106 test, 94%) |
| D0-T8 | ruff (lint+format) + mypy + pre-commit — 17 hook toza |
| D0-T9 | GitHub Actions CI — sifat, testlar, Docker obrazi |
| D0-T10 | Deploy to'plami — bootstrap, server compose, deploy workflow, runbook |

| D1-T2 | `Category` + 8 kategoriya fixture'i + ikonka shabloni |
| D1-T3 | `Complaint` — slug, status, hot_score, denormalizatsiya |
| D1-T4 | `Solution` — bitta muammoda bitta qabul qilingan yechim (baza kafolati) |
| D1-T5 | `ComplaintVote` / `SolutionVote` + `cast_vote()` |
| D1-T6 | Anonimlik invarianti — `public_author` + guard testlar |
| D1-T7 | Lenta: Qaynoq/Yangi/Eng yaxshi/Yechilgan + kategoriya va avlod filtri (holat URL'da) |
| D1-T8 | HTMX ovoz berish — `<form>` ustiga qo'shilgan qatlam, JS'siz ham ishlaydi |

**D0-T10 qisman:** barcha fayllar tayyor va lokal repetitsiyada tekshirilgan;
server hali olinmagan. Ketma-ketlik: [`DEPLOY.md`](DEPLOY.md).

Keyingi: **M1** — D1-T1 (Telegram login), D1-T9/T10 (formalar),
D1-T11 (hot_score + Celery beat), D1-T12 (kursor sahifalash), D1-T14 (N+1).

---

## Ochiq qarorlar

- `apps/accounts/services.py` → `telegramdan_username_yasash()` —
  Telegram'dan foydalanuvchi nomi qanday yasalsin? (D1-T1 uchun)
- To'liq ro'yxat: `def_tasks.json` → `ochiq_qarorlar`

## Vaqtinchalik fayllar

- `apps/common/maket.py` — maket sahifalarini ko'rish uchun dev URL'lari.
  M1 oxirida **o'chiriladi**; URL nomlari (`feed`, `complaint_detail`, ...)
  o'sha nomlar bilan ilova `urls.py` fayllariga ko'chadi, ya'ni shablonlarga
  qayta tegilmaydi.
