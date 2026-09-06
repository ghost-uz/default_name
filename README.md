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

### ⚠️⚠️ Dev'da shablon tahriri ko'rinmasligi (tuzatildi)

`runserver --noreload` bilan shablonni tahrirlab, sahifani yangilaganda
**hech narsa o'zgarmasdi**. Sabab: Django `loaders` berilmaganda
`cached.Loader` ni o'zi qo'shadi — shablon fayli bir marta o'qiladi va
jarayon tugagunicha xotirada qoladi.

`OPTIONS["debug"] = True` buni **o'chirmaydi** (u faqat xato sahifasiga
tegadi). Endi `config/settings/dev.py` loaderlarni **ochiq** belgilaydi
(`APP_DIRS = False` + `filesystem` va `app_directories`).

⚠️ Bu ikki marta vaqt yedi: o'zgarish qo'llanmadi deb o'ylanib, kod
qayta-qayta tekshirildi.

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
| D1-T9 | Muammo yaratish/tahrirlash — server validatsiyasi, 30 daqiqalik oyna, qoralama avtosaqlash |
| D1-T10 | Yechim yozish va qabul qilish + `KarmaEvent` jurnali (D3-T1 qisman) |
| D1-T11 | `hot_score` algoritmi + Celery beat (har 10 daqiqada, 7 kunlik oyna) |
| D1-T12 | Kursor sahifalash (`?after=<pk>`) + HTMX «Yana yuklash» |
| D1-T1 | Telegram login — HMAC, `auth_date`, `state` nonce, avtomatik username |
| D1-T13 | Saqlanganlar (xatcho'p) — `SavedComplaint` + `/saqlanganlar/` |
| D1-T14 | N+1 auditi — so'rov soni element soniga bog'liq emasligi qotirildi |

**M1 (yadro) TO'LIQ TUGADI** — 14/14 task.

| Task | Nima |
|---|---|
| D2-T3 | Ko'rinish invarianti — ikki qatlamli guard (`visible()` majburlanadi) |
| D2-T1 | Shikoyat (`Report`) modeli va oqimi — eskalatsiya navbatni o'zgartiradi, ko'rinishni emas |
| D2-T2 | Moderatsiya navbati — obyekt bo'yicha guruhlangan holatlar, klaviatura, qaytariladigan qarorlar |
| D2-T4 | Tezlik cheklovi — Redis'da, paketsiz; chegaralar sozlamada, 429 + tushunarli xabar |
| D2-T5 | Spam evristikasi — honeypot, forma vaqti, havola soni; shubhali kontent yashirilmaydi |
| D2-T7 | O'zgarmas audit jurnali — to'rt qatlamli himoya, staff sahifasi |
| D2-T6 | ⚠️ Inqirozli kontent — aniqlash, yordam bloki, moderator qo'llanmasi (**qisman**: rasmiy raqam ochiq) |
| D2-T9 | CSP (nonce bilan) va xavfsizlik sarlavhalari — `unsafe-inline` siz |
| D2-T8 | Hisobni o'chirish (anonimlashtirish) va ma'lumot eksporti (JSON, fon vazifasi) |
| D2-T10 | ⚠️ Huquqiy sahifalar va rozilik — sana **va versiya** saqlanadi (**qisman**: matnlar yuristsiz) |
| D2-T11 | Bloklash va uch ogohlantirish — foydalanuvchi bloki + moderator cheklovi, ikkalasi **boshqa-boshqa narsa** |

**M2 (xavfsizlik va moderatsiya) KOD BO'YICHA TUGADI** — 11/11 task yozildi.
Ikkitasi `qisman` bo'lib qoladi va ularning ochiq qismi **koddan tashqarida**:
D2-T6 rasmiy ishonch telefonini talab qiladi, D2-T10 — yurist xulosasini.

| Task | Nima |
|---|---|
| D3-T1 | Karma ledgeri — ovoz karmasi (+2), qabul (+15), kompensatsiya (idempotent) |
| D3-T4 | Profil sahifasi — tablar MANZILDA, anonim postlar begonaga ko'rinmaydi |
| D3-T5 | ExpertProfile va tasdiqlash — hujjat `MAXFIY_ROOT` da, qaror bilan o'chadi |
| D3-T2 | Nishonlar — shart = METRIKA + CHEGARA (ma'lumotda), qulf faqat egasiga |
| D3-T3 | Oylik reyting — KESHDAN keladi, Celery soatiga bir hisoblaydi |

**M3 (gamifikatsiya va profil) TO'LIQ TUGADI** — 5/5 task.

| Task | Nima |
|---|---|
| D4-T1 | PostgreSQL FTS — GENERATED `tsvector`, GIN + trigram indeks, qayta indekslash buyrug'i |
| D4-T2 | Lotin/kiril transliteratsiyasi va apostrof — to'qqiz yozuv usuli, bitta lexema |
| D4-T3 | Qidiruv sahifasi `/qidiruv/` — ajratish, uch filtr, yaqin so'zlar takliflari |
| D4-T4 | SEO asoslari — kanonik, Open Graph, avtomatik yasaladigan OG rasm |
| D4-T5 | `sitemap.xml` va `robots.txt` — faqat ko'rinadigan kontent |
| D4-T6 | Schema.org QAPage (JSON-LD) — Google natijada javobni ko'rsatadi |
| D4-T7 | O'xshash muammolar — fon vazifasida hisoblanadi, keshdan ko'rsatiladi |

**M4 (qidiruv va SEO) TO'LIQ TUGADI** — 7/7 task.

| Task | Nima |
|---|---|
| D5-T1 | Bildirishnomalar markazi — ichki kanal, sarlavhada o'qilmaganlar belgisi |
| D5-T2 | Telegram bot — fon vazifasi, qayta urinish, bloklanganni belgilash |
| D5-T3 | Kanalga avto-post — kuniga 3 ta qaynoq savol, takrorsiz, muallifsiz |
| D5-T4 | Bildirishnoma sozlamalari — tur bo'yicha yoqish/o'chirish, jim soatlar |
| D5-T5 | Ekspertlarga «javobsiz savollar» dayjesti — haftada bir marta, faqat o'z sohasi |
| D6-T1 | Obuna modeli va PRO cheklovlari — `user.has_pro` yagona manba |
| D6-T5 | Kontakt almashinuvi — yopiq suhbat, ikki tomonlama rozilik |
| D7-T4 | Ish faoliyati byudjeti — so'rov/hajm QAT'IY, vaqt ogohlantiradi |

---

### To'liq matnli qidiruv (D4-T1)

Uch qatlam, har biri o'zi eng ishonchli bo'lgan joyda:

| Qatlam | Nima qiladi | Qayerda |
|---|---|---|
| Normallashtirish | kichik harf, diakritika olib tashlanadi | Python (`apps/common/matn.py`) |
| `tsvector` | lexemalar + vaznlar (sarlavha `A`, tavsif `B`) | PostgreSQL (GENERATED ustun) |
| Chegara | "qanchalik yaqin — yetarli yaqin" | sozlama (`QIDIRUV_OXSHASHLIK_CHEGARASI`) |

```bash
python manage.py qidiruvni_yangilash            # qayta indekslaydi
python manage.py qidiruvni_yangilash --tekshir  # faqat sanaydi, yozmaydi
```

O'lchangan (10 041 post): FTS **6.8 ms**, trigram zaxira yo'li **43 ms** —
qabul mezoni 200 ms.

### ⚠️⚠️ Normallashtirish Python'da, `unaccent` kengaytmasida EMAS

Task tavsifi `'simple' + unaccent` degan va uni bazada qilish tabiiy
ko'rinadi. Lekin **`unaccent()` PostgreSQL'da `IMMUTABLE` emas** — u lug'at
faylini o'qiydi. Ya'ni uni GENERATED ustun ifodasiga qo'yib bo'lmaydi:
Postgres ochiq rad etadi.

Odatdagi chetlab o'tish — o'zining `IMMUTABLE` deb e'lon qilingan o'ram
funksiyasi — **yolg'on va'da**: lug'at almashsa indeks jimgina noto'g'ri
bo'lib qoladi va buni hech narsa bildirmaydi.

Python'da qilish bu tuzoqni butunlay yo'q qiladi va bitta qo'shimcha foyda
beradi: **indekslash va qidiruv aynan bir kod yo'lidan o'tadi**. Baza
tomonda esa faqat immutable `to_tsvector('simple', …)` qoladi.

### ⚠️ `simple` tokenizatori apostrofda so'zni BO'LADI

Bu D4-T2 ning sababi va u jonli bazada o'lchangan:

```sql
to_tsvector('simple', 'ko''chmas mulk')  ->  'ko':1 'chmas':2 'mulk':3
to_tsvector('simple', 'kochmas mulk')    ->  'kochmas':1 'mulk':2
```

Ikkinchisi bilan birinchisini qidirsangiz — **topilmaydi**. Ya'ni apostrofni
qanday ishlash "chiroyli qo'shimcha" emas, indeksning asosiy qarori.

D4-T2 da apostrof **o'chiriladi** (bir shaklga keltirilmaydi): shunda
`ko'chmas`, `koʻchmas`, `kochmas` va `кўчмас` — hammasi bitta lexemaga
tushadi. Bu foydalanuvchilarning apostrofsiz yozish odatini ham qamrab
oladi.

### ⚠️⚠️ `bulk_create` IKKI narsani chetlab o'tadi

`bulk_create` va `bulk_update` `save()` ni chaqirmaydi **va signal ham
yubormaydi**. `Complaint` uchun bu ikkita hisoblanadigan maydonni
yo'qotadi:

1. **qidiruv ustunlari** — post lentada ko'rinadi, qidiruvda esa YO'Q.
   Xato chiqmaydi, log toza.
2. **slug** — ⚠️ bu **D1-T3 dan beri ochiq turgan teshik edi** va uni
   D4-T1 testi topdi. Barcha yozuvlar bo'sh slug oladi, ikkinchisi esa:

   ```
   duplicate key value violates unique constraint "complaint_slug_uniq_alive"
   DETAIL: Key (slug)=() already exists
   ```

   Ya'ni D7-T7 (sovuq start, 50-100 post ommaviy kiritiladi) **bitta
   postdan keyin to'xtardi** va sabab birinchi qarashda tushunarsiz
   bo'lardi: "slug'ni hech kim bo'sh qoldirmagan-ku".

Ikkalasi ham `ComplaintQuerySet` da yopildi. Bu teshik tanlangan dizayndan
kelib chiqadi: `search_vector` GENERATED ustun bo'lgani uchun uni unutish
mumkin emas, lekin **normallashtirish baribir Python'da qoladi** — trigger
bermaydigan bo'shliq aynan shu yerda.

### Ish faoliyati byudjeti (D7-T4)

Byudjet **bitta jadvalda**: `apps/common/byudjet.py`. Uning o'zgarishi
`git diff` da ko'rinadi va shu bilan «sekin o'sish» ko'rinadigan bo'ladi.

```
manage.py byudjet          # HAQIQIY ma'lumot ustida hisobot
```

| sahifa | so'rov | bayt |
|---|---|---|
| lenta (mehmon) | 2 / **4** | 128 KB / **150 KB** |
| lenta (kirgan) | 7 / **9** | 135 KB / **160 KB** |
| dard (batafsil) | 5 / **8** | 44 KB / **60 KB** |
| qidiruv | 3 / **5** | 123 KB / **145 KB** |

### ⚠️⚠️ Qaysi o'lcham yiqitadi, qaysi biri ogohlantiradi

| O'lcham | Xulq | Sabab |
|---|---|---|
| so'rov soni | **yiqitadi** | to'liq deterministik |
| javob hajmi | **yiqitadi** | to'liq deterministik |
| aktiv hajmi | **yiqitadi** | to'liq deterministik |
| render vaqti | ogohlantiradi | runner yuki tasodifiy |
| Lighthouse | ogohlantiradi | ballar ±5 tebranadi |

Deterministik o'lchamlar **yolg'on yiqitmaydi** — ya'ni ularni qattiq
ushlash mumkin va kerak. Vaqtni qat'iy chegara qilish CI'ni haftada bir
necha marta yolg'on yiqitardi, va **uchinchi yolg'on ogohlantirishdan
keyin hech kim natijaga qaramaydi**.

⚠️ Render testida **ikki chegara**: ogohlantirish (300 ms) va falokat
(10×, qat'iy). Ikkinchisi ataylab — chegarasiz test hech qachon yiqila
olmasdi.

### ⚠️ Hajm byudjeti Lighthouse'ning katta qismini deterministik qoplaydi

Lighthouse «Performance» balli asosan **bayt va so'rovlar** funksiyasi.
CSS ikki barobar o'ssa yoki sahifaga ulkan inline SVG qo'shilsa — buni
brauzersiz va tebranishsiz ushlaymiz. Lighthouse ishi uning ustiga
a11y, SEO va best-practices baholarini qo'shadi (`continue-on-error`).

### ⚠️ `manage.py byudjet` CI'da ishlatilmaydi

CI bazasi faqat migratsiyalardan iborat va **bo'sh** — u yerdagi o'lchov
ma'nosiz raqamlar berardi. CI'da byudjetni **pytest** tekshiradi (u
realistik ma'lumot yaratadi); buyruq esa dasturchi vositasi.

### Kontakt almashinuvi — yopiq suhbat (D6-T5)

Yechim qabul qilingandan keyin har ikki tomon **shaxsiy suhbat** taklif
qila oladi. So'rov o'zi hech narsa ochmaydi — faqat qarshi tomonning
roziligi ochadi (`/suhbatlar/`).

### ⚠️⚠️ «Kontakt almashinuvi» emas, «yopiq suhbat»

Task ikki yo'lni taklif qildi. Ikkinchisi tanlandi va sabab bitta so'z
bilan: **qaytarib bo'lmaslik**.

Telegram nomini bergan odam uni **orqaga ola olmaydi**. Uy zo'ravonligi
yoki qarz haqida anonim yozgan odam uchun bu platformadagi eng xavfli
amal bo'lardi — va D2-T11 dagi `UserBlock` ham foydasiz bo'lib qolardi:
qarshi tomonda sizning nomingiz allaqachon bor.

Yopiq suhbat esa **qaytariladi**: yopish, bloklash, shikoyat qilish
mumkin. Qabul mezoni «chat moderatsiya qamrovida» ham faqat shu yo'lda
bajariladi — Telegram'ga ko'chgan suhbatni moderatsiya qila olmaymiz.

### ⚠️⚠️ Suhbat ichida ham anonimlik saqlanadi

Anonim muallif suhbatda ham **«Anonim»** bo'lib qoladi. Ya'ni qabul
mezoni «anonim muallifning kontakti roziligisiz ochilmaydi» eng kuchli
shaklda bajariladi: kontakt **umuman ochilmaydi**, faqat taxallusli
kanal ochiladi.

Ism har doim kontentning `public_author` idan olinadi — bu anonimlik
invariantining **to'rtinchi joyi** (shablon, OG, JSON-LD dan keyin) va
eng oson unutiladiganlaridan biri: «baribir kim ekanini biladi» degan
taxmin **noto'g'ri**, anonim muallifni qarshi tomon hech qachon
bilmagan.

⚠️ Shablonda `xabar.korsatiladigan_nom` ishlatiladi.
`xabar.author.display_name` **yozmang**.

### ⚠️ Chat moderatsiya qamrovida

`Xabar` — `ContentModel`, ya'ni shikoyat (D2-T1), navbat (D2-T2), uch
ogohlantirish (D2-T11), audit jurnali (D2-T7) va **inqiroz aniqlash**
(D2-T6) bepul keladi. Oxirgisi bu yerda alohida qimmatli: eng og'ir gap
aynan shaxsiy yozishmada aytiladi va u ommaviy lentada hech qachon
ko'rinmaydi.

`Report` va `ModerationAction` ga uchinchi FK (`xabar`) qo'shildi —
ContentType emas, ochiq qaror Q1 bilan izchil.

⚠️ Moderator navbatda **faqat shikoyat qilingan xabarni** ko'radi, butun
suhbatni emas: shikoyat kirish sababi bo'lsa ham, u butun yozishmani
ochish uchun asos bermaydi. Admin'da ham xabarlar `inline` qilinmagan.

### Obuna va PRO (D6-T1)

`payments.Subscription` (OneToOne, `user.obuna`) — reja, holat, boshlanish,
tugash, avto-yangilash. Kunlik Celery vazifasi muddati o'tganlarni
`TUGAGAN` deb belgilaydi.

### ⚠️⚠️ Ikki xil «PRO» — bitta so'z, ikki boshqa tushuncha

| | `User.has_pro` | `ExpertProfile.pro_faolmi` |
|---|---|---|
| Ma'nosi | **to'lov** amalda | PRO **nishoni** ko'rsatiladi |
| Kimga | har qanday foydalanuvchi | faqat ekspert |
| Sharti | faol obuna | tasdiqlangan malaka **va** `has_pro` |

Ikkinchisi birinchisining **iste'molchisi**, parallel manba emas. D3-T5
qoidasi kuchda qoladi: tasdiqlanmagan odam pul to'lab «Tasdiqlangan PRO»
nishonini **ololmaydi**.

`ExpertProfile.pro_until` **olib tashlandi** — uni qoldirish aynan
taskning `nega` bo'limidagi holatni yasardi: ikkita sana, biri
yangilanadi, ikkinchisi unutiladi.

### ⚠️⚠️ Celery — tozalash, haqiqat manbai emas

`Subscription.faolmi` **holatni ham, muddatni ham** tekshiradi. Faqat
`status` ga qarasak, muddat tugagan payt bilan vazifaning keyingi ishga
tushishi orasida obuna **bir kungacha bepul** uzayardi. Vazifa umuman
ishlamasa ham hech kim bepul PRO olmaydi.

Manba kodi guard'i (`apps/payments/tests_guard.py`) `apps/payments/` dan
tashqarida `expires_at` / `auto_renew` ga tegishni **taqiqlaydi** — ataylab
bo'lsa `# pro-istisno: <sabab>` izohi qo'yiladi.

### ⚠️ Bekor qilish darhol to'xtatmaydi

Bekor qilish = `auto_renew = False`; holat **`FAOL` bo'lib qoladi** va
muddat tugagach vazifa uni yopadi. Darhol to'xtatish «bekor qilish»
tugmasini **jazoga** aylantirardi: oyning boshida bekor qilgan odam 29
kunini yo'qotardi.

Shu mantiqda uzaytirish ham **qolgan muddat ustiga** qo'shiladi —
`now + 30` erta to'lagan mijozni jazolardi.

### ⚠️⚠️ Jim soatlarda kechiktirish BIR MARTALIK (D5-T4 tuzatildi)

Bu xato D6-T1 ustida ishlaganda, soat 22:00 dan o'tgan paytda fosh
bo'ldi. Eager rejimda (testlar) `apply_async` `countdown` ni e'tiborsiz
qoldirib vazifani **darhol** qayta ishga tushiradi — u yana jim soatga
tushib, yana o'zini chaqirardi (`RecursionError`).

14 ta **aloqasiz** test yiqildi va to'plam 87s dan 331s ga cho'zildi —
kod ham, testlar ham o'zgarmagan holda, **faqat soat** o'zgargani uchun.

Ishlab chiqarishda ham foyda: oyna sozlamasi buzuq bo'lsa xabar
**cheksiz** kechikardi; endi eng yomon holatda bir marta kechikadi va
yuboriladi.

⚠️ Testlar endi devor soatiga bog'liq emas: `conftest` jim oynani nol
kenglikka qo'yadi, oynani sinaydigan testlar uni **oshkora** e'lon
qiladi.

### Ekspert dayjesti (D5-T5)

Haftada bir marta tasdiqlangan ekspert **o'z sohasidagi** javobsiz
savollar ro'yxatini oladi (`DAYJEST_SAVOL_SONI`, oyna
`DAYJEST_OYNA_KUNLARI`). Soha — `ExpertProfile.specialty`, ya'ni
`Category` ga FK (D3-T5): ikkinchi taksonomiya yaratilmadi.

Dayjest **yangi `BildirishnomaTuri`** sifatida qilingan, to'g'ridan-to'g'ri
Telegram chaqiruvi emas. Shu qaror bilan u D5-T4 infratuzilmasini bepul
meros oldi: sozlama bilan o'chirish, jim soatlar, bloklangan foydalanuvchi
belgisi, qayta urinish — hech biri qayta yozilmadi.

### ⚠️⚠️ Inqiroz savoli dayjestga chiqmaydi — D5-T3 dan boshqa sababga ko'ra

Kanalda (D5-T3) sabab **kuchaytirish** edi: minglab odamga tarqatish. Bu
yerda auditoriya bitta malakali odam, ya'ni u dalil ishlamaydi.

Haqiqiy sabab — **asbob noto'g'ri**: dayjest haftalik va «ish navbati»
shaklida keladi. Shoshilinch yordamga muhtoj odamni olti kun kutadigan
navbatga qo'yish ikki marta xato: yordam kechikadi, va biz uni
«bajariladigan ish» qatoriga tushiramiz. Inqirozga javob — D2-T6 dagi
darhol ko'rsatiladigan telefonlar.

### ⚠️ Eng uzoq kutgan savol birinchi

Maqsad «bu haftada nima bo'ldi» emas, **javobsiz savollarni kamaytirish**.
Yangisidan boshlansa, band kategoriyada eski savollar hech qachon
ro'yxatga tushmasdi — har hafta yangilari ustidan bosardi.

Takror **ataylab**: javob berilmagan savol keyingi haftada yana chiqadi.
Dayjest — yangiliklar lentasi emas, **ish navbati**. Oyna uni cheklaydi:
umidsiz eski savol o'zi tushib qoladi.

### ⚠️ Ro'yxat saqlanmaydi, yuborish paytida qayta hisoblanadi

Jim soatlar (D5-T4) xabarni ertalabgacha kechiktiradi. Saqlangan ro'yxat
o'shanda allaqachon javob olgan savollarni ko'rsatardi va ekspertni
bekorga yugurtirardi. Ro'yxat bo'shab qolsa xabar **umuman
yuborilmaydi** — «javobsiz savol yo'q» degan xabar aynan botdan chiqib
ketishga olib keladigan shovqin.

Shu sababdan bildirishnoma matnida **sanoq yo'q**: ko'rsatilgan raqam
ko'rsatilgan ro'yxatga teng bo'lishi kerak (M3 invarianti), ro'yxat esa
jonli.

### Bildirishnoma sozlamalari (D5-T4)

`/bildirishnomalar/sozlama/` — har tur uchun alohida katakcha va «jim
soatlar» (`JIM_SOATLAR_BOSHI` -> `JIM_SOATLAR_OXIRI`, standart
22:00-08:00, **mahalliy** vaqtda).

Standart holatda faqat `MUHIM_TURLAR` yoqiq. Ro'yxat **ataylab yopiq**:
yangi tur qo'shilganda u standart holatda **o'chiq** bo'ladi — tanlov
ehtiyotkor tomonga xato qiladi, chunki ortiqcha bildirishnoma botdan
chiqib ketishga olib keladi va **u qaytmaydi**.

### ⚠️⚠️ Sozlama yetkazishni boshqaradi, yozuvni emas

O'chirilgan tur uchun ham `Notification` **yaratiladi** — faqat Telegram
xabari yuborilmaydi.

Ichki markaz (D5-T1) — **zaxira** kanal. «Telegram'da bezovta qilmang»
degan odam «menga umuman aytmang» demagan: u saytga kirganda nima
bo'lganini ko'rishi kerak. Yozuvni ham to'xtatish tarixni yo'q qilardi
va uni qaytarib bo'lmasdi.

### ⚠️⚠️ Jim soatda xabar kechiktiriladi, tashlanmaydi

«Tunda yubormaslik» ni «umuman yubormaslik» deb tushunish oson va
noto'g'ri: foydalanuvchi tunda bezovta qilinmaslikni so'radi, xabardan
voz kechishni emas.

Kechiktirish `apply_async(countdown=...)` bilan, `self.retry()` bilan
**emas**: jim soat xato emas va u `max_retries` hisobini yeb qo'yardi —
ertalab Telegram'da haqiqiy nosozlik bo'lsa urinish qolmasdi.

### ⚠️ Jim oyna yarim tundan o'tadi

22:00 -> 08:00 oynasida oddiy `boshlanish <= hozir < tugash` taqqoslash
**har doim `False`** beradi — va xato bermaydi, shunchaki jimgina «jim
soat yo'q» deydi. `jim_vaqtmi()` ikkala holatni ham qaraydi.

### Kanalga avto-post (D5-T3)

Celery beat kuniga bir marta eng qaynoq **3 ta** savolni Telegram
kanaliga chiqaradi (`TELEGRAM_CHANNEL_ID`). Har post
`kanalga_yuborilgan_at` bilan belgilanadi — bittasi ikki marta chiqmaydi.

### ⚠️⚠️ Kanalda muallif ko'rsatilmaydi — hatto ochiq postda ham

Kanal posti **qaytarib olinmaydi**: u yuz minglab odamga bir zumda
ko'rinadi va Telegram'da o'chirilgan xabar ham allaqachon o'qilgan
bo'ladi. Ya'ni bu yerdagi xato — anonimlik invariantining eng qimmat
buzilishi.

Shuning uchun `post_matni()` `public_author` ga **ham** murojaat
qilmaydi: kanal posti **savolni** ko'rsatadi, odamni emas.

### ⚠️⚠️ Inqiroz belgisi bor post kanalga chiqmaydi

D2-T6 siyosati aniqlangan postni **o'chirmaydi va yashirmaydi** — u
saytda odatdagidek turadi. Lekin uni minglab odamga **o'zimiz**
tarqatish butunlay boshqa narsa: bu odamning eng og'ir daqiqasini
ommaviy tomoshaga aylantirardi.

Farq nozik va muhim: biz kontentni **cheklamaymiz**, lekin uni
**kuchaytirmaymiz** ham.

### ⚠️ Belgi har postdan keyin, yuborishdan keyin

Ikki tartib qarori, ikkalasi ham xatoning narxi bo'yicha tanlangan:

| Qaror | Aks holda |
|---|---|
| belgi **har post**dan keyin | vazifa o'rtasida uzilsa yuborilganlar belgilanmay qolardi va **qayta chiqardi** |
| belgi **yuborishdan keyin** | yuborish yiqilganda post «chiqqan» deb qolib, **hech qachon chiqmasdi** |

Ikki xatodan kamroq zararlisi tanlangan: takror emas, o'tkazib yuborish.

### Telegram bildirishnomasi (D5-T2)

Bildirishnoma yozilgach Celery vazifasi uni Telegram'ga uzatadi. Xato
turlari ajratiladi: **bloklangan** (doimiy), **vaqtinchalik** (qayta
urinish), **boshqa** (jurnalga).

```bash
TELEGRAM_BOT_TOKEN=...   # bo'sh bo'lsa xabar yuborilmaydi — bu xato EMAS
SAYT_MANZILI=...         # prod'da ALLOWED_HOSTS dan olinadi
```

⚠️ Yangi paket **qo'shilmadi**: bitta `POST` va bitta JSON javob uchun
stdlib `urllib` yetarli.

### ⚠️⚠️ Vazifa `transaction.on_commit()` orqali navbatga tushadi

`yechim_yozish` va `accept_solution` — ikkalasi ham `@transaction.atomic`.
Vazifa to'g'ridan-to'g'ri `delay()` qilinsa, worker uni **commit
bo'lgunicha** olishi mumkin va o'shanda bildirishnoma bazada hali yo'q —
vazifa «topilmadi» deb tugardi.

Xato **tasodifiy** bo'lardi: sekin bazada o'tib ketardi, yuk ostida esa
qaytalanardi.

### ⚠️⚠️ Istisnolarda manzil yo'q — token o'sha yerda

Telegram API'da token **manzilning ichida**:
`https://api.telegram.org/bot<TOKEN>/sendMessage`. Uni istisno matniga,
jurnalga yoki Sentry'ga qo'shish — **bot tokenini oshkor qilish**.

`URLError` manzilni o'zi qo'shishi mumkin, shuning uchun faqat istisno
turi nomi yoziladi. Buni guard test qo'riqlaydi.

### ⚠️ 403 da foydalanuvchi belgilanadi

`User.telegram_bloklandi` qo'yiladi va keyingi xabarlar **umuman**
yuborilmaydi — aks holda navbat bitta odam uchun cheksiz aylanardi.

Bayroq **kirishda** tozalanadi: Telegram blokdan chiqarilganini xabar
qilmaydi, login vidjeti esa o'sha botning nomidan ishlaydi. Bu
evristika, lekin muqobili — bayroqni mangu qoldirish, ya'ni odam botni
qayta ochsa ham hech qachon xabar olmasligi.

### Bildirishnomalar markazi (D5-T1) — `/bildirishnomalar/`

Sarlavhadagi qo'ng'iroqda o'qilmaganlar soni (keshdan), markazda ro'yxat.
Ro'yxat ochilganda hammasi o'qilgan deb belgilanadi.

⚠️ **Nega ichki markaz kerak, Telegram yetarli emas.** Telegram
bildirishnomasi (D5-T2) tezroq ochiladi, lekin unga tayanib bo'lmaydi:
foydalanuvchi botni bloklashi yoki Telegram'dan umuman chiqib ketishi
mumkin — o'shanda u yechim kelganini **hech qachon** bilmaydi. Ichki
markazni bloklab bo'lmaydi.

### ⚠️⚠️ Anonim manbada `actor` bazaga ham yozilmaydi

«Ismni ko'rsatmaymiz» degan yondashuv (yozib qo'yib, shablonda yashirish)
bu loyihada **uch marta** muammo bo'lgan: D1-T6 (shablon), OG metalari,
JSON-LD. Bildirishnomada qoida qattiqroq — **yozuvning o'zi qolmaydi**,
ya'ni uni admin, eksport (D2-T8) yoki kelajakdagi API ham oshkor qila
olmaydi.

Matn o'shanda «Kimdir muammoingizga yechim yozdi» bo'ladi — va bu
**to'g'ri** matn.

### ⚠️ Ro'yxat o'qilgan deb belgilashdan OLDIN olinadi

Teskari tartibda foydalanuvchi qaysi bildirishnoma **yangi** ekanini ko'ra
olmasdi: sahifa ochilgan zahoti hammasi «eski» bo'lib qolardi va ro'yxat
mutlaqo bir xil ko'rinardi. Endi shu sahifada yangilari ajratiladi,
keyingi tashrifda esa ular oddiy qatorga aylanadi.

### ⚠️ Sanoq shablon tegi orqali, kontekst-protsessor emas

Kontekst-protsessor qiymatni **har** renderga qo'shadi — jumladan HTMX
qismlariga (ovoz kartasi, «yana yuklash»), ular esa sarlavhani umuman
chizmaydi. Bu D1-T14 da qotirilgan so'rov byudjetiga bekorga qo'shilardi.

### O'xshash muammolar (D4-T7)

Detal sahifasining yon panelida uchta yaqin savol. **Hisoblash fon
vazifasida**: selektor faqat keshdan o'qiydi va kesh bo'sh bo'lsa vazifani
navbatga qo'yib, bo'sh ro'yxat qaytaradi.

### ⚠️⚠️ Trigram o'rniga FTS — o'lchangan qaror

Task tavsifida «trigram o'xshashligi» deb yozilgan va u birinchi bo'lib
sinaldi, lekin jonli ma'lumotda ishlamadi: butun sarlavhalar bo'yicha
`similarity()` **mavzuviy yaqinlikni emas, harflar ustma-ustligini**
o'lchaydi.

| Usul | To'g'ri natija | Begona |
|---|---|---|
| `similarity()` | 0.140 | 0.118 |
| FTS + to'xtash so'zlar | **0.152** | **0.008** |

Trigram D4-T1 da o'z joyini topgan — u yerda **qisqa** so'rov uzun
sarlavha bilan solishtiriladi va aynan shunda ishlaydi.

### ⚠️ To'xtash so'zlar — faqat o'xshashlik uchun

PostgreSQL'ning `simple` konfiguratsiyasida to'xtash so'zlar yo'q (o'zbek
lug'ati ham yo'q). Ro'yxatsiz «nima», «bo'ladi», «oydan», «beri» kabi
so'zlar reytingni shishiradi.

⚠️ Ro'yxat **qidiruvga qo'llanmaydi**: foydalanuvchi «nima qilay» deb
qidirsa, u shu so'zlarni **topishni** kutadi.

### ⚠️⚠️ Keshda `pk` lar turadi, ko'rsatish ma'lumoti emas

Sarlavhani keshlash bitta so'rovni tejardi, lekin post keshlangandan
**keyin** yashirilsa, yon panel unga havola berishda davom etardi —
ko'rinish invarianti (D2-T3) kesh muddati (24 soat) davomida buzilardi.
`pk` lar esa har so'rovda `visible()` dan qayta o'tadi.

### ⚠️ Kesh so'rov-sanog'i testlarini buzadi (ikkinchi marta)

`sorovlar()` birinchi so'rov bilan keshni ilitadi va ikkinchisini
o'lchaydi. O'xshash post **topilgan** bo'lsa ikkinchi so'rovda bitta
qo'shimcha `pk__in` so'rovi bo'ladi, topilmagan bo'lsa — yo'q. Ya'ni
o'lchov yechimlar soniga emas, **kesh holatiga** bog'liq bo'lib qoladi.

Yechim: test yordamchilari keshni **aniq holatga** qo'yadi.

### Schema.org QAPage (D4-T6)

Muammo sahifasida `application/ld+json` bloki: `Question` +
`acceptedAnswer` / `suggestedAnswer`, ovoz soni bilan. Google natijada
javobning o'zini ko'rsatishi mumkin — M4 dagi eng yuqori daromadli SEO
ishi.

### ⚠️ Javobsiz savolga QAPage yozilmaydi

Google `QAPage` uchun **kamida bitta javob** kutadi. Javobsiz savolda
`acceptedAnswer` ham, `suggestedAnswer` ham bo'lmaydi va Rich Results
Test **xato** beradi. Shuning uchun blok umuman chiqarilmaydi — sahifa
baribir indekslanadi (kanonik va OG joyida), javob paydo bo'lgan zahoti
blok ham paydo bo'ladi.

### ⚠️⚠️ JSON-LD — anonimlik invariantining uchinchi joyi

Anonim postda `author` maydoni **umuman chiqarilmaydi**. Bu eng oson
unutiladigan joy, chunki **JSON-LD sahifada ko'rinmaydi**: buzilganini
na foydalanuvchi, na dasturchi sezadi — u faqat Google indeksida qoladi.

Xuddi shu sabab yashirilgan yechim uchun ham amal qiladi: ro'yxat
`complaint_detail` dan (ko'rinish filtridan o'tgan holda) keladi va
`schema.py` **o'zi so'rov qilmaydi**.

### ⚠️ `</script>` blokdan chiqa olmaydi

JSON ichidagi `</script>` ketma-ketligi brauzer uchun skript blokini
**shu yerda** tugatadi va qolgan matn HTML bo'lib o'qiladi — ya'ni
foydalanuvchi matni orqali teg kiritish mumkin bo'lardi. `<`, `>` va `&`
kodlanadi (Django'ning `json_script` filtri ishlatadigan jadval).

⚠️ `nonce` shart: CSP `script-src` `<script>` elementiga **turidan qat'i
nazar** qo'llanadi, Googlebot esa Chrome asosida ishlaydi.

### ⚠️ N+1 boshqa mavzudagi o'zgarishdan keldi

`_javob()` dastlab `yechim.complaint.get_absolute_url()` orqali yurardi.
`complaint_detail` yechimlarni faqat `select_related("author")` bilan
oladi — natijada **har yechim uchun bitta qo'shimcha so'rov**. D1-T14
qo'riqchisi (uchta test) darhol yiqildi.

Eng muhimi: regressiya **butunlay boshqa mavzudagi** (SEO) ishdan keldi.
Shuning uchun N+1 guardi qat'iy son emas, **bog'liqlik** tekshiradi.

### `sitemap.xml` va `robots.txt` (D4-T5)

Uch bo'lim: muammolar (`visible()`), faol kategoriyalar va statik
sahifalar. Yashirilgan, tekshiruvdagi (`PENDING`) va o'chirilgan kontent
**chiqmaydi** — bu D4-T5 ning butun ma'nosi: sitemap'ga tushgan yashirin
post Google tomonidan indekslanadi va yashirishning ma'nosi qolmaydi.

### ⚠️⚠️ Sitemap va kanonik bir-biriga bog'langan

Kategoriya sahifalari sitemap'ga `/?category=moliya` shaklida tushadi —
**aynan kanonik bergan shaklda**. Boshqa loyihada bu juftlik buzilgan va
Search Console barcha kategoriya sahifalarini «Duplicate, not canonical»
deb rad etgan: sitemap ish bermagan, faqat ogohlantirish yaratgan.

Shuning uchun integratsion test **sitemapdagi har bir manzilni ochadi va
uning kanonigi bilan solishtiradi** — biri o'zgarsa, ikkinchisi ham
o'zgarishi kerak bo'ladi.

### ⚠️ `robots.txt` da admin manzili YO'Q

`robots.txt` — **ommaviy** fayl. Unga `Disallow: /maxfiy-panel/` deb
yozish admin panel manzilini butun dunyoga e'lon qilish degani.
`DJANGO_ADMIN_URL` aynan shuning uchun sozlanadigan qilingan: standart
`/admin/` eng ko'p skanerlanadigan yo'l va uni o'zgartirish arzon himoya
qatlami — robots.txt ga yozish o'sha himoyani bir qatorda yo'q qilardi.

Admin baribir indekslanmaydi: u login talab qiladi.

⚠️ `Disallow` — **yashirish emas, skanerlashni tejash**. Haqiqiy himoya
har doim kodda (avtorizatsiya, `visible()`).

⚠️ Yangi ommaviy sahifa qo'shilsa `StatikSitemap.YOLLAR` ga qo'lda
qo'shiladi — u URLconf'dan avtomatik olinmaydi (sabab modul
docstring'ida).

### SEO va ijtimoiy tarmoq kartasi (D4-T4)

Har sahifada kanonik manzil va to'liq Open Graph to'plami. Muammo
sahifasining OG rasmi **fon vazifasida** yasaladi — sarlavha va
kategoriyadan.

```bash
python manage.py og_standart              # static/img/og-default.png
python manage.py og_rasmlarni_yangilash   # hammasini qayta yasaydi
python manage.py og_rasmlarni_yangilash --faqat-yoqlar
```

### ⚠️⚠️ Kanonikda faqat `?category=` qoladi

| Parametr | Kanonikda | Sabab |
|---|---|---|
| `category` | ✅ qoladi | "Moliya bo'yicha dardlar" — o'z mazmuni bo'lgan sahifa |
| `sort` | ❌ | bir xil kontent, boshqa tartib |
| `generation` | ❌ | qolsa 8 kategoriya × 3 avlod = 24 ta yupqa sahifa |
| `after`, `sahifa` | ❌ | sahifalash |
| `q` | — | qidiruv sahifasi `noindex`, kanonik umuman bermaydi |

⚠️ Kanonikni **faqat `request.path` dan** qurish oson va noto'g'ri:
o'shanda `/?category=moliya` bosh sahifaga kanoniklashadi va Search
Console uni **«Duplicate, not canonical»** deb indeksdan chiqaradi —
ya'ni kategoriya sahifalari qidiruvda umuman ko'rinmaydi.

### ⚠️ Shrift vendorlangan — `assets/fonts/`

OG rasmini yasash uchun **shrift fayli shart**: `python:3.12-slim` da
hech qanday shrift yo'q. Tizim shriftiga tayanish «lokalda ishlaydi,
konteynerda quti chizadi» holatini yaratardi.

- **Inter** (OFL) — saytning o'z shrifti **va** kirillni qamrab oladi;
- ikkita **statik** fayl (Regular + Bold), kerakli belgilarga
  qisqartirilgan — jami **252 KB**;
- `assets/`, **`static/` emas**: shrift faqat server tomonida ishlatiladi,
  `static/` da tursa `collectstatic` uni yig'ib nginx uni bekorga
  tarqatardi.

⚠️ **Nega o'zgaruvchan (variable) shrift emas.** Bitta fayldan to'qqizta
og'irlik olish jozibali ko'rinadi, lekin u 876 KB va kerakli belgilarga
qisqartirilgandan keyin ham **513 KB** — `gvar` jadvali qisqarmaydi.
`check-added-large-files` hooki (500 KB) uni to'g'ri rad etdi. Chegarani
ko'tarish yoki istisno qo'shish mumkin edi, ikkalasi ham qo'riqchini
bo'shatardi; to'g'ri yechim — bizga faqat ikki og'irlik kerak ekanini tan
olish. Qanday yasalgani: [`assets/fonts/README.md`](assets/fonts/README.md).

⚠️ Shriftda yo'q belgi **bo'sh quti** bo'lib chiziladi — xato chiqmaydi,
va buni faqat Telegram'ga havola tashlagan odam ko'radi. Shuning uchun
qamrov testi bor: lotin, o'zbek `ʻ`, apostrofning 7 varianti, kirill
(`ў қ ғ ҳ`).

### ⚠️ OG rasm fayl nomida mazmun hashi bor

Ijtimoiy tarmoqlar `og:image` ni **manzil bo'yicha** keshlaydi. Nom
o'zgarmasa (`og/12.png`), sarlavha tahrirlangandan keyin ham Telegram
**eski** rasmni ko'rsatishda davom etardi. `og/12-a1b2c3d4.png` esa
mazmun o'zgarganda manzilni ham o'zgartiradi — va o'zgarmasa yangi fayl
to'planmaydi.

### Qidiruv sahifasi (D4-T3) — `/qidiruv/?q=…`

Natijalar dolzarblik bo'yicha, uch filtr (soha / avlod / holat), topilgan
so'zlar ajratilgan, bo'sh natijada — yaqin so'zlar takliflari.

### ⚠️⚠️ `SearchHeadline` bu loyihada ISHLAMAYDI

Ajratib ko'rsatishning tabiiy yo'li — Postgres'ning `SearchHeadline` i.
D4-T2 dan keyin u ikkala shaklda ham buzuq:

| Manba | Nima bo'ladi |
|---|---|
| `SearchHeadline("qidiruv_sarlavha", …)` | ekranda **normallashtirilgan** matn: bosh harfsiz, apostrofsiz, kirilcha post lotinchaga aylangan holda |
| `SearchHeadline("title", …)` | so'rov normallashtirilgan, matn xom → **kirilcha postda hech narsa ajratilmaydi** |

Yechim — **so'z darajasida ajratish** (`apps/common/ajratish.py`): asl matn
so'zlarga bo'linadi, har bir so'z **aynan o'sha** `qidiruv_uchun()` bilan
normallashtiriladi va so'rov so'zlari bilan solishtiriladi. Ekranda esa
**asl** so'z qoladi:

```
"Ипотека олиш"  +  q="ipoteka"   ->   <mark>Ипотека</mark> олиш
```

⚠️ Ikkinchi normallashtirish implementatsiyasi paydo bo'lmaydi — qoidalar
o'zgarsa ajratish avtomatik ergashadi. Buning sharti guard test bilan
qotirilgan: **so'z bo'yicha normallashtirish butun matnnikiga teng
bo'lishi kerak**. `qidiruv_uchun()` ga kontekstga bog'liq yangi qoida
qo'shilsa, o'sha test darhol yiqiladi.

### ⚠️ Qidiruvda sahifalash — offset, kursor emas

Lentada kursor ishlatiladi (D1-T12), qidiruvda esa **`?sahifa=2`**. Sabab
texnik va majburiy: kursor saralash **maydonlariga** tayanadi
(`hot_score`, `created_at`, `id`), qidiruv esa **dolzarblik** bo'yicha
saralanadi — u hisoblanadi va model maydoni emas.

Xuddi shunday, `COUNT(*)` lentada ataylab yo'q, qidiruvda ataylab bor:
«12 ta natija» — so'rov qanchalik aniq bo'lganini ko'rsatadigan signal.

### ⚠️ Qidiruv sahifasi `noindex`

`q` × soha × avlod × holat × sahifa — cheksiz kombinatsiya. Indekslansa
sayt o'z-o'zi bilan raqobatlashadigan minglab sifatsiz sahifa hosil
qilardi. D4-T5 sitemap'i ham bu yerga kirmaydi.

### To'qqiz yozuv usuli — bitta so'z (D4-T2)

O'zbekistonda bitta odam bir kuni lotin, ertasiga kirill yozadi, apostrofni
esa klaviaturasi qanday qo'ysa shunday qo'yadi. Qidiruv uchun bularning
hammasi **bitta shaklga** kelishi kerak:

```
ko'chmas   ko‘chmas   ko’chmas   koʻchmas
koʼchmas   ko`chmas   ko´chmas   kochmas   кўчмас
                        ↓
                     kochmas
```

Bittasi ham chetda qolsa, qidiruv foydalanuvchining **klaviaturasiga**
bog'liq bo'lib qoladi — va buni tushuntirib bo'lmaydi.

### ⚠️ Apostrof o'chiriladi, bir shaklga keltirilmaydi

Bu D2-T6 dagi qaror bilan **ataylab teskari** (`normallashtir()` apostrofni
saqlaydi, chunki inqiroz kalit so'zlari apostrofli yozilgan). Ikki sabab,
ikkalasi ham o'lchangan:

1. `simple` tokenizatori apostrofda so'zni bo'ladi (yuqoriga qarang);
2. foydalanuvchilar apostrofni ko'pincha **umuman yozmaydi**.

⚠️ Narxi bor va u ongli qabul qilingan: `to'y` va `toy` bir xil bo'lib
qoladi. Qidiruvda **qamrov aniqlikdan muhimroq** — topilmagan natija
foydalanuvchi uchun "sayt buzuq" degani, ortiqcha natija esa ro'yxatning
ikkinchi qatori.

### ⚠️ Transliteratsiya aksentdan OLDIN, apostrof NFKC dan OLDIN

Ikkala tartib ham xatodan keyin qotirilgan:

| Noto'g'ri tartib | Nima bo'lardi |
|---|---|
| aksent → transliteratsiya | `ё` avval `е` ga aylanardi → `yo` o'rniga `e`; `й` NFKD da `и`+breve ga parchalanib `i` bo'lardi |
| NFKC → apostrof | `´` (U+00B4) ning **moslik dekompozitsiyasi** bor: NFKC uni bo'shliq + birikuvchi urg'uga aylantiradi va jadval unga yetib bormaydi |

⚠️ Ikkinchisi **D2-T6 ga ham tegishli edi**: `o´ldirmoqchiman` inqiroz kalit
so'ziga mos kelmasdi, chunki so'z `o` va `ldirmoqchiman` ga bo'linib
ketardi. D4-T2 testi topdi.

### ⚠️ `е` va `ц` kontekstga bog'liq

Rasmiy o'zbek transliteratsiyasi, va bu qoidasiz kirillcha kontent lotincha
so'rovga mos kelmaydi:

```
Европа  ->  yevropa      берди  ->  berdi
цирк    ->  sirk         абзац  ->  abzats
```

### ⚠️ Normallashtirish o'zgarsa — migratsiya, qo'lda qadam emas

`qidiruv_sarlavha` / `qidiruv_tavsif` — **saqlangan** qiymat. Qoidalar
o'zgargach yangi postlar yangi shaklda, eskilari esa eski shaklda qoladi va
qidiruv yarim ishlaydigan holatga tushadi — **xatosiz**.

Shuning uchun D4-T2 o'zgarishi `0006_qidiruv_transliteratsiya` migratsiyasi
bilan keladi: u `entrypoint` da avtomatik ishlaydi. Deploy'da qo'lda
bajariladigan qadam bir kuni albatta unutiladi.

`manage.py qidiruvni_yangilash` esa ta'mirlash va tekshirish uchun qoladi.

### ⚠️ O'xshashlik chegarasi sozlamada, Postgres GUC'ida emas

Xato yozilgan so'rov (`ipotaka` → `ipoteka`) uchun `word_similarity`
ishlatiladi — oddiy `similarity` emas:

```
similarity('ipotaka', 'ipoteka olish qiyinmi')       = 0.20   ← ishlamaydi
word_similarity('ipotaka', 'ipoteka olish qiyinmi')  = 0.50
```

Indeksli `<%` operatori chegarani `pg_trgm.word_similarity_threshold` dan
oladi va uning standarti **0.6** — ya'ni yuqoridagi 0.50 ni o'tkazib
yuborardi. Uni o'zgartirish esa **ulanish holatiga yozish** degani:
`CONN_MAX_AGE=60` bilan ulanishlar qayta ishlatiladi, `SET` so'rovlar
orasida oqib ketardi va buni test ushlamasdi.

Shuning uchun oshkora taqqoslash ishlatiladi: indeksdan foydalanmaydi,
lekin chegara ko'rinadigan mahsulot parametri bo'lib qoladi va bu yo'l
faqat asosiy qidiruv bo'sh qaytganda ishlaydi.

### ⚠️⚠️ Uch marta qaytgan bitta teshik: ANONIMLIK va SANOQLAR

M3 ning uchta taskida BIR XIL muammo boshqa shaklda qaytdi. Har safar
qoida bitta: **ko'rsatilgan raqam ko'rsatilgan ro'yxatga teng bo'lsin.**

| Qayerda | Teshik | Yechim |
|---|---|---|
| **D3-T4** profil sanoqlari | "18 dard" desa-yu 12 tasi ko'rinsa → 6 ta anonim post borligi chiqadi | Begonaga sanoq ham anonimsiz |
| **D3-T4** karma tarixi | `KarmaEvent` yechimga FK — tarix "shu anonim yechim shu odamniki" xaritasini berardi | Faqat egasiga |
| **D3-T2** nishon progressi | Progress ommaviy bo'lsa, ayirma anonim ishning ANIQ sonini berardi | Qulf va progress faqat egasiga |

⚠️ **D3-T2 da qoldiq teshik ONGLI qabul qilindi**: olingan nishon
ommaviy va chegarasi ma'lum, ya'ni *"kamida N ta anonim ish bor"* degan
**noaniq** xulosa mumkin. To'liq yopish uchun nishon faqat ochiq ishni
sanashi kerak edi — bu esa anonim javobni jazolardi va D3-T1 dagi karma
qaroriga zid bo'lardi.

### ⚠️ Uchta tizim, uchta xil "cheklangan odam" qarori

Bir xil savolga (moderator cheklovi nimaga ta'sir qiladi?) uchta
boshqa javob — va ular ziddiyat emas:

| | Cheklovda nima bo'ladi | Nega |
|---|---|---|
| **Ekspert nishoni** (D3-T5) | **Qoladi** | Tasdiq — MALAKA haqida, cheklov — XULQ haqida |
| **Yutuq nishonlari** (D3-T2) | **Qoladi** | Yutuq — TARIX, joriy holat emas |
| **Oylik reyting** (D3-T3) | **Chiqariladi** | Reyting — TAVSIYA: platformaning "bu odamga qarang" degan gapi |

Chegara: odamning **yozuvi** tegilmaydi, platformaning **tavsiyasi**
esa to'xtatiladi.

### Bloklash: ikki xil "blok" (D2-T11)

⚠️⚠️ **Bitta so'z, ikki butunlay boshqa tushuncha.** Ular ataylab
ajratilgan — bitta jadvalga qo'shilsa "bloklangan odam nega yoza
olmayapti?" degan buglar chiqardi.

| | `User.is_banned` | `UserBlock` |
|---|---|---|
| Kimning qarori | **Platformaning** | **Foydalanuvchining** |
| Oqibati | Odam **yoza olmaydi** | Odam boshqasini **ko'rmaydi** |
| Bloklangan biladimi | Ha — sayt bo'ylab banner | **Yo'q**, hech qanday signal yo'q |
| Yo'nalishi | — | **Bir tomonlama** |
| Kim qo'yadi | Moderator yoki avtomatika | Foydalanuvchining o'zi |

**Nega bir tomonlama:** ikki tomonlama qilish "meni bloklashdi" degan
signalni berardi va tortishuvni kuchaytirardi — bloklashdan maqsad esa
aksincha.

**Nega bloklangan odamga aytilmaydi:** u hech qanday cheklov olmaydi va
xabardor ham emas. Bu jazo emas, bu o'z lentangizni tozalash.

### Uch ogohlantirish — sanash mashinaning ishi

```
1-2 chora  ->  hech narsa
3-chora    ->  7 kunga cheklov   (CHEKLOV_CHEGARASI)
5-chora    ->  doimiy blok       (DOIMIY_BLOK_CHEGARASI)
```

Chegaralar `config/settings/base.py` da — kod tegilmaydi (D2-T4 bilan bir xil qoida).

⚠️ **`RAD_ETISH` sanalmaydi** — u "qoidabuzarlik yo'q" degani.
⚠️ **Bekor qilingan chora sanalmaydi** — moderatorning xatosi
foydalanuvchining "jinoyat tarixiga" aylanmasin.

⚠️⚠️ **Oqibat tugmani bosishdan OLDIN aytiladi.** Navbatda "keyingi chora
muallifni AVTOMATIK cheklaydi" degan qator chiqadi. Moderator
ogohlantirmoqchi edi, bloklamoqchi emas — buni keyin bilib olishi
noto'g'ri.

### ⚠️ Cheklov muddati QISQARMAYDI

`apps/moderation/services.py::yangi_muddat()` — `max(mavjud, so'ralgan)`.

Sodda `now + kun` yozuvi **jim yumshatish** berardi: moderator odamni 30
kunga cheklagan bo'lsa-yu, ikki kundan keyin standart 7 kunlik cheklov
tushsa, muddat **21 kunga qisqarardi**. Ya'ni yangi jazo jazoni
yengillashtirardi.

Muddatlar **qo'shilmaydi** ham (30 + 7 + 7 → yashirin doimiy blok
bo'lardi, lekin "doimiy" deb atalmagan holda — bunday blokni
tushuntirib ham, apellyatsiya qilib ham bo'lmaydi).

### ⚠️⚠️ Anonimlik blokdan ustun

Bloklangan muallif **lentadan chiqadi**, muhokamada esa javobi
`<details>` ichida yig'iladi ("Bloklangan foydalanuvchi javobi —
ko'rsatish"). Javob **o'chirilmaydi**: olib tashlansa "3 yechim" yozilgan
joyda 2 tasi ko'rinardi va javoblar zanjiri uzilardi.

**Lekin anonim javob HECH QACHON yig'ilmaydi**, muallifi bloklangan
bo'lsa ham. "Bloklangan foydalanuvchi javobi" yozuvi o'quvchiga muallif
KIM ekanini aytib qo'yardi — u o'z bloklaganlari ro'yxatini biladi.
Ya'ni blok anonimlikni ochadigan asbobga aylanardi.

Lentada bunday xavf yo'q: u yerda post shunchaki **yo'q** bo'ladi va
yo'qlik signal bermaydi.

### ⚠️ `values().annotate()` + oshkora tartib = jim buzilgan GROUP BY

`_qoidabuzarlik_sonlari()` dagi **`.order_by()` ni olib tashlamang**.

`values(...).annotate(...)` da so'rovdagi **oshkora** tartib maydoni
GROUP BY ga qo'shiladi. O'lchandi (Django 6.1):

```
.order_by("created_at").values_list("target_author_id").annotate(Count("pk"))
  -> GROUP BY 1, "created_at"   -> [(4,1), (4,1), (21,1), (21,1)]   ❌

.order_by().values_list("target_author_id").annotate(Count("pk"))
  -> GROUP BY 1                 -> {4: 2, 21: 2}                    ✅
```

Har chora o'ziga alohida guruh bo'ladi, **hamma sanoq `1`** chiqadi va
**hech qanday xato bermaydi**: so'rov bajariladi, ma'lumot qaytadi,
faqat raqamlar yolg'on bo'ladi.

⚠️ **`Meta.ordering` esa GROUP BY ga TUSHMAYDI** — Django 3.1 dan beri
guruhlashda e'tiborga olinmaydi. Bu bo'limning birinchi versiyasi aynan
`Meta.ordering` ni aybdor deb yozgan edi va **noto'g'ri edi**; o'lchov
ikkala shakl ham bir xil SQL berishini ko'rsatdi. Xulosa o'zgarmadi
(`.order_by()` qolsin — u **kelajakda** yuqoriga qo'shiladigan oshkora
tartibdan himoya), lekin sabab boshqa.

Qo'riqchi: `test_navbat_sanogi_OSHKORA_TARTIBDAN_buzilmaydi` — u buzilgan
shaklni **ataylab qurib**, farqni ko'rsatadi.

### Hisobni o'chirish va eksport (D2-T8) — `/hisob/`

⚠️⚠️ **Hisob qatori o'chirilmaydi — anonimlashtiriladi.**

| O'chadi | Qoladi |
|---|---|
| username, `telegram_id`, ism, bio, email | dardlar va yechimlar |
| ovozlar va xatcho'plar | karma tarixi |
| shikoyatlarda `reporter` | audit jurnali (D2-T7 — dalil) |

Kontent qoladi, chunki u **boshqa odamlarga ham tegishli**: kimdir
savol berib, siz javob bergansiz. Javobni o'chirish o'sha odamning
savolini javobsiz qoldirardi.

⚠️ **Nega bitta umumiy «sentinel» foydalanuvchi emas** (reja shuni
taklif qilgandi): u holda barcha o'chirilgan hisoblarning kontenti
bitta muallifga tegishli bo'lib qolardi va bir suhbatda ikki xil odam
bir xil nom bilan chiqib, «o'zi bilan o'zi gaplashayotgan» odam
taassurotini berardi. Har hisobga o'z o'rindoshi qoladi.

Muallif nomi `User.display_name` orqali chiqadi — bitta joyda
tuzatilsa hamma joyda to'g'ri bo'ladi.

---

### ⚠️ Eksportga boshqa odamlarning ma'lumoti kirmaydi

Vasvasa katta — «menga tegishli hamma narsa» deb postga kelgan
shikoyatlarni, kim ovoz berganini va kim javob yozganini qo'shib
yuborish oson. Lekin bu **boshqa odamlarning** ma'lumoti bo'lardi va
eksport ularning roziligisiz shaxsiy ma'lumot tarqatadigan quvurga
aylanardi.

Shuning uchun: shikoyatlarda `reporter` yozilmaydi, ovozlar faqat
**son** sifatida chiqadi.

⚠️ **Email emas, yuklab olish:** kirish faqat Telegram orqali va
foydalanuvchida email **yo'q** — xat yuborish yo'li umuman mavjud emas.

⚠️ Eksport **7 kundan keyin o'chiriladi** (beat vazifasi). «Bir marta
so'ralgan, keyin unutilgan» fayl bazada yillab turishi — ma'lumot
sizishining eng oddiy yo'li.

---

### CSP va xavfsizlik sarlavhalari (D2-T9)

Yo'nalishlar `settings.CSP_YONALISHLARI` da. Nonce va sarlavha bitta
middleware'da (`apps/common/middleware.py::CSPMiddleware`) — ikkiga
bo'linsa ular uzilib ketishi va **barcha inline skript jimgina
bloklanishi** mumkin.

⚠️⚠️ **Telegram qatorlarini olib tashlamang.** Vidjet
`https://telegram.org` dan skript yuklaydi va ichkarida
`https://oauth.telegram.org` iframe'ini ochadi. Ikkalasi ham CSP'da
ochiq bo'lmasa, «Telegram orqali kirish» tugmasi **umuman chiqmaydi** —
sahifa esa xatosiz ko'rinadi va sabab faqat konsolda qoladi.

⚠️ **`style-src` da `'unsafe-inline'` yo'q va shunday qolishi kerak.**
Buning uchun uchta shart bajarilgan:

1. Shablonlarda inline `style=` **yo'q** (ikkitasi D2-T9 da sinfga
   ko'chirildi: `.stagger-1..19` va `.xavfsiz-past`). Guard test
   taqiqlaydi.
2. HTMX o'zining inline `<style>` blokini kiritmaydi —
   `base.html` da `{"includeIndicatorStyles": false}`, uslublar esa
   `input.css` da (`.htmx-indicator`).
3. Barcha inline skriptlar `nonce` oladi.

⚠️ **CSP hamma muhitda bir xil**, dev'da ham. Faqat prodda yoqilsa,
buzilish faqat prodda ko'rinardi. Narxi: `DEBUG` dagi Django xato
sahifasi uslubsiz ko'rinadi — traceback o'qilaveradi.

---

### ⚠️ Sozlamani ikki marta yozmang

`base.py` da xavfsizlik bo'limi allaqachon bor. D2-T9 da beshta
sozlama ikkinchi marta yozilgan edi va bu **jim xato**: Python'da
oxirgi yozuv g'olib chiqadi, birinchisi esa vakolatli bo'lib
ko'rinadi. Amalda u `SECURE_REFERRER_POLICY` ni `same-origin` dan
bo'shroq qiymatga o'zgartirib yuborardi.

Buni `test_csp.py::test_sozlamalarda_TAKROR_YOQ` (AST) qo'riqlaydi.

---

### ⚠️ Inqirozli kontent (D2-T6)

Kalit so'z aniqlash → post **navbatning eng tepasiga** chiqadi va
sahifada yordam bloki ko'rinadi.

⚠️⚠️ **Aniqlash — tsenzura emas.** Aniqlangan post **o'chirilmaydi,
yashirilmaydi** va muallif **hech qanday ogohlantirish olmaydi**. Task
tavsifi buni ochiq aytadi: «jim o'chirish eng yomon variant — u odamni
yakkalaydi».

⚠️ **Yolg'on ijobiy ataylab ko'p.** Ro'yxat keng va aniqlik qurbon
qilingan: noto'g'ri aniqlangan post moderatorning bir daqiqasini oladi,
o'tkazib yuborilgani esa odamni yolg'iz qoldiradi. **Ro'yxatni
qisqartirmang** — buni alohida test qo'riqlaydi.

⚠️ **Apostrof normallashtirish majburiy.** O'zbek lotin yozuvida
apostrof kamida to'rt xil belgi bilan yoziladi (`'` `ʻ` `‘` `` ` ``).
Normallashtirmasak, aniqlash foydalanuvchining **klaviaturasiga**
bog'liq bo'lib qolardi. Uch alifbo qamralgan: o'zbek lotin, o'zbek
kirill, rus.

**Moderator qo'llanmasi:** `/moderatsiya/qollanma/` — navbatdan va
shoshilinch holat kartasidan bir bosish narida. Qo'llanma kod ichida
ataylab: alohida hujjatda turgani tungi soat 2 da topilmaydi.

---

### ⚠️⚠️ `ISHONCH_TELEFONI` ataylab bo'sh

```python
ISHONCH_TELEFONI = None  # config/settings/base.py
```

Task eslatmasi: **«noto'g'ri inqiroz raqami raqam yo'qligidan
xavfliroq»**. Javob bermaydigan raqamga qo'ng'iroq qilgan odam ikkinchi
marta urinmaydi.

Bu yerga **faqat rasmiy manbadan tasdiqlangan** ishonch liniyasi
yoziladi. Loyiha egasining shaxsiy raqami bu yerga yozilmaydi —
inqirozdagi odamga tayyorgarliksiz odam javob berishi xavfli
(2026-08-29 da aniqlashtirilgan; u `ALOQA_TELEFONI` sifatida alohida
turadi).

Raqam yo'q bo'lsa ham blok ishlaydi: **103** va **112** har doim
ko'rsatiladi.

To'ldirish uchun:

```python
ISHONCH_TELEFONI = {"nom": "<tashkilot>", "raqam": "<raqam>", "vaqt": "24/7"}
```

…va `test_ISHONCH_TELEFONI_sozlamada_BOSH` testini yangilang — bu
to'ldirishni **ongli qadam** qiladi, tasodifiy emas.

---

### Audit jurnali (D2-T7) — `/moderatsiya/jurnal/`

`AuditLog` — staff harakatlarining **o'zgarmas** yozuvi: kim, nima,
qachon, sabab. Nizo yoki huquqiy so'rov chiqqanda jurnal yagona dalil
bo'ladi.

**O'zgarmaslik to'rt qatlamda:**

| Qatlam | Nima yopiq |
|---|---|
| `AuditLog.save()` | mavjud yozuvni saqlash |
| `AuditLog.delete()` | bitta yozuvni o'chirish |
| `AuditQuerySet.update()` / `.delete()` | **ommaviy** o'zgartirish |
| `AuditLogAdmin` | qo'shish, tahrirlash, o'chirish |

⚠️ Uchinchi qator eng oson unutiladigani:
`AuditLog.objects.filter(...).update(izoh="")` **hech qanday model
metodini chaqirmaydi**, ya'ni `save()` dagi himoya uni ushlamaydi.

⚠️ **Cheklov:** himoya ORM darajasida. To'g'ridan-to'g'ri SQL (`psql`)
yozuvni baribir o'zgartira oladi — haqiqiy kafolat baza triggeri yoki
`REVOKE UPDATE, DELETE ON moderation_auditlog`. **Deploy paytida
qo'shilsin.**

---

### ⚠️ Jurnalga yozish ikki yo'l bilan — ataylab

| Yo'l | Nima uchun |
|---|---|
| **Signal** (`ModerationAction` `post_save`) | Kontent ustidagi chora eng muhim yozuv; qo'lda chaqirishga qoldirilsa bir kuni unutilardi |
| **`audit()` chaqiruvi** | Staff amallarining hammasi ham model yaratmaydi (shikoyat yopish, kelajakda bloklash) — ilinadigan signal yo'q |

Faqat bittasiga tayanish ikkala holatda ham teshik qoldirardi.

`tests_audit.py` dagi **AST guard** `services.py` dagi staff-himoyali
funksiyalarni sanaydi va yangi xizmat qo'shilganda **yiqiladi** — ya'ni
jurnal testini yozishga majbur qiladi.

---

### ⚠️ `actor_nomi` — denormalizatsiya majburiy

`actor` FK `SET_NULL`: hisob o'chirilsa u `None` bo'ladi. Audit jurnali
uchun aynan shu ma'lumotni yo'qotish mumkin emas — **«kim qildi?»
savoliga javobsiz jurnal dalil emas.** Shuning uchun ism yozuv paytida
nusxalanadi.

---

### Spam evristikasi (D2-T5)

`apps/common/spam.py`. Yozish formalari `SpamHimoyaliForm` dan meros
oladi va ikkita ko'rinmas maydon qo'shadi: honeypot va **imzolangan**
forma-ochilish vaqti.

| Signal | Ball |
|---|---|
| Honeypot to'ldirilgan | **rad etiladi** |
| 3 soniyadan tez to'ldirilgan | 3 |
| 1 soniyadan tez | 4 |
| Vaqt belgisi yo'q / imzo buzilgan | 3 |
| 2 havola / 3–4 havola / 5+ havola | 1 / 2 / 3 |
| Hisob 24 soatdan yosh | 1 |

Chegara — **3 ball**. Ya'ni «3 soniyadan tez» yolg'iz o'zi yetadi (qabul
mezoni), yangi hisob esa yolg'iz o'zi yetmaydi.

⚠️⚠️ **Shubhali kontent yashirilmaydi** — mahsulot qarori. Post e'lon
qilinadi va odamlar uni ko'radi; faqat moderatsiya navbatiga holat
tushadi (`avtomatik_belgilash`). Sabab: yolg'on ijobiy holatning narxi
bu yerda spamnikidan yuqori. Spam bir necha soat ko'rinib tursa —
noqulay; og'ir dardini yozgan odamning posti jimgina yo'qolsa — u
boshqa qaytmaydi.

⚠️ **Yagona rad etadigan signal — honeypot.** Ko'rinmaydigan maydonni
odam to'ldira olmaydi; bu mexanik aniqlik. Boshqa hech qanday signal,
hattoki ularning yig'indisi ham, kontentni rad etmaydi: «1 soniyada
to'ldirilgan» odamni ham ko'rsatishi mumkin — matnni boshqa joyda
yozib qo'yib, nusxa ko'chirgan odam.

---

### ⚠️⚠️ Honeypot maydonining nomi — eng nozik joy

Nomi **`website` / `email` / `url` / `phone` bo'lmasligi kerak.**
Brauzer va parol menejerlari aynan shunday nomlarni **avtomatik
to'ldiradi**, maydon ko'rinmasa ham. Natijada honeypot haqiqiy
odamlarni ushlab, eng yomon turdagi yolg'on ijobiy berardi: odam hech
narsa qilmagan, posti esa rad etilgan.

Hozirgi nom — `qoshimcha_izoh` (autofill uchun ma'nosiz, «hamma
maydonni to'ldiruvchi» botlar uchun farqi yo'q). Buni alohida test
qotirib qo'yadi.

⚠️ `display: none` **ataylab ishlatilmagan**: e'tiborliroq botlar
hisoblangan uslubni tekshirib bunday maydonni o'tkazib yuboradi.
Ekrandan tashqariga chiqarish DOM'da oddiy ko'rinadi.

⚠️ CSS yetarli emas — maydonda `tabindex="-1"` (klaviatura) va
`aria-hidden="true"` (ekran o'quvchi) ham bor. Uch qatlamning har biri
tekshiriladi.

---

### ⚠️ Vaqt belgisi imzolangan, eskirgani esa shubhali emas

Belgi `django.core.signing` bilan imzolanadi: oddiy `hidden` maydon
bo'lsa, skript qiymatni o'tmishga surib «sekin to'ldirdim» deb
ko'rsatardi.

Eskirgan belgi (7 kundan oshgan) **shubhali emas** — u «juda uzoq
to'ldirilgan» degani, bot xulqiga umuman o'xshamaydi. Qoralamani saqlab
qo'yib, ertasiga davom ettirgan odam jazolanmasligi kerak.

---

### ⚠️ Tizim shikoyati — `Report` ga `reporter=None`

Avtomatik filtr alohida model yaratmaydi: navbat allaqachon `Report`
ustiga qurilgan (D2-T2), ya'ni guruhlash, tartiblash, choralar va
bekor qilish bepul keladi.

Navbat kartasida avtomatik signal **«avtomatik filtr»** belgisi bilan
ajratiladi — «uchta odam shikoyat qildi» va «bizning filtr shubhali
dedi» butunlay boshqa dalillar, va ikkalasi bir xil ko'rinsa moderator
evristikaga odamga bergan ishonchni berardi.

---

### Tezlik cheklovi (D2-T4)

Chegaralar `config/settings/base.py` dagi **`TEZLIK_CHEKLOVLARI`** da —
kodda emas. Shakl: `"<son>/<[koeffitsiyent]><birlik>"`, birlik
`s|m|h|d`. Masalan `"30/m"` = daqiqasiga 30 marta, `"5/2h"` = ikki
soatda 5 marta.

| Nuqta | Foydalanuvchi | IP |
|---|---|---|
| Ovoz berish | 30/daqiqa | 120/daqiqa |
| Post yozish | 5/soat | 20/soat |
| Yechim yozish | 20/soat | 60/soat |
| Shikoyat | 10/soat | 40/soat |
| Xatcho'p | 60/daqiqa | 200/daqiqa |

⚠️ **IP chegaralari ataylab bo'sh.** O'zbekistonda mobil operatorlar
CGNAT ishlatadi — bitta tashqi IP ortida minglab abonent bo'lishi
mumkin. Tor IP chegarasi butun mahallani bloklardi va sabab
tashqaridan umuman ko'rinmasdi («menda ishlamayapti, do'stimda
ishlayapti»). Asosiy og'irlik **foydalanuvchi** chegarasida; bu
munosabat alohida test bilan qotirilgan.

⚠️ **Faqat yozish so'rovlari sanaladi** (POST/PUT/PATCH/DELETE). Aks
holda «soatiga 5 ta post» chegarasi formani 6 marta **ochgan** odamni
bloklardi.

⚠️ **Kesh ishlamasa so'rov o'tadi** (fail open). Redis nosozligi butun
saytni «yozib bo'lmaydigan» holatga tushirmasligi kerak — tezlik
cheklovi yumshatish chorasi, xavfsizlik chegarasi emas.

---

### ⚠️⚠️ `ISHONCHLI_PROKSILAR_SONI` — deploy paytida tekshiring

Mijoz IP'si `apps/common/ratelimit.py::mijoz_ip` da aniqlanadi va bu
yerda **ikkita teskari xato** bor, ikkalasi ham jim:

| Xato | Oqibati |
|---|---|
| `REMOTE_ADDR` ni ishlatish | Nginx ortida u **har doim nginx manzili** — butun sayt bitta hisobga tushadi va IP chegarasi hammani birdan bloklaydi |
| `X-Forwarded-For` ga so'zsiz ishonish | Sarlavhani **mijoz o'zi yozadi** — har so'rovda boshqa qiymat yuborgan skript cheklovga umuman urilmaydi |

Yechim — ishonchli proksilar soni. Nginx
`$proxy_add_x_forwarded_for` bilan ro'yxat **oxiriga** o'ziga ulangan
manzilni qo'shadi, ya'ni bitta proksi bo'lsa mijoz IP'si oxirgi
element; undan chapdagilarni mijoz o'zi yozgan bo'lishi mumkin va ular
e'tiborga olinmaydi.

```python
ISHONCHLI_PROKSILAR_SONI = 0  # dev/test — REMOTE_ADDR
ISHONCHLI_PROKSILAR_SONI = 1  # prod — nginx
ISHONCHLI_PROKSILAR_SONI = 2  # CDN (Cloudflare) + nginx
```

⚠️ Bu son proksilar sonidan **katta bo'lmasligi** kerak: har bir
ortiqcha birlik mijoz o'zi yozgan sarlavhaga ishonish degani.

---

### ⚠️ HTMX 2xx bo'lmagan javobni DOM'ga qo'ymaydi

Server 429 qaytarsa foydalanuvchi uchun **hech narsa bo'lmaydi**:
tugma bosiladi, ovoz o'zgarmaydi, xato ham chiqmaydi — odam qayta-qayta
bosadi va cheklovni yanada chuqurroq buzadi.

Shuning uchun `app.js` (12-bo'lim) `htmx:responseError` ni ushlab, 429
matnini toast qilib ko'rsatadi. JavaScript'siz yo'lda esa `429.html`
to'liq sahifa sifatida qaytadi.

⚠️ Sahifaning ohangi ayblovchi **emas**: chegaraga urilganlarning
aksariyati hujumchi emas, bir necha marta bosgan yoki ulanishi uzilgan
odam.

---

### ⚠️ Testlarda kesh tozalanadi

`conftest.py` dagi `_keshni_tozalash` **autouse** fixture'ini olib
tashlamang. Kesh baza kabi qaytarilmaydi, tezlik cheklovi kaliti esa
foydalanuvchi `pk` va `127.0.0.1` dan quriladi — ikkalasi ham testlar
orasida takrorlanadi.

Usiz eng yomon turdagi xato chiqadi: testlar **alohida** o'tadi, birga
ishlatilganda tasodifiy 429 bilan yiqiladi — va yiqiladigan test
aybdoridan butunlay boshqa faylda bo'ladi.

---

### Moderatsiya navbati (D2-T2) — `/moderatsiya/`

Staff uchun. Boshqalarga **404** (403 emas: 403 manzil borligini
tasdiqlab beradi va qidirish uchun boshlang'ich nuqta bo'ladi).

⚠️ **Navbat shikoyat bo'yicha emas, OBYEKT bo'yicha guruhlanadi.**
Admin shikoyatlarni birma-bir ko'rsatadi: bitta postga 5 ta shikoyat
kelsa, moderator bir xil kontentni 5 marta o'qib, 5 marta bir xil qaror
qabul qiladi. Qaror esa kontent haqida, shikoyat haqida emas — shuning
uchun bitta qaror obyektning **barcha** ochiq shikoyatlarini yopadi.

**Tartib** (mahsulot qarori):

| # | Guruh | Ichida |
|---|---|---|
| 1 | `XAVF` sababi bor | har doim tepada |
| 2 | SLA buzilgan (>24 soat) | eskisidan yangisiga |
| 3 | Qolganlari | shikoyat soni ko'pdan kamga |

24 soat — tasodifiy son emas: shikoyat sahifasi foydalanuvchiga aynan
shuni va'da qiladi. 2 va 3 ataylab teskari mantiqda — faqat son bo'lsa
yolg'iz haqiqiy shikoyat cheksiz kutardi, faqat vaqt bo'lsa tez
tarqalayotgan zarar navbat oxirida qolardi.

**Klaviatura:** `j`/`k` holatlar, `i` izoh, `Esc` chiqish, `1`…`4`
choralar (yengildan og'irga), `?` yordam. Bu **qo'shimcha qatlam** —
hammasi haqiqiy `<button>`/`<input>`, ya'ni Tab + Enter bilan ham to'liq
ishlaydi. Matn yozayotganda qisqa tugmalar o'chadi.

---

### ⚠️ Moderator qarori qaytariladi, jurnal esa o'chirilmaydi

`ModerationAction` — **faqat qo'shiladi**. Bekor qilish yozuvni
o'chirmaydi: jurnalga `BEKOR_QILISH` turidagi yangi yozuv qo'shiladi va
u `bekor_qiladi` orqali asl qarorga bog'lanadi (`KarmaEvent` dagi
kompensatsiya naqshi bilan bir xil).

Nima uchun bu muhim: klaviatura bilan tez ishlash **chalkashishni ham**
tezlashtiradi. Bitta noto'g'ri tugma — va odam o'zining eng og'ir
shaxsiy postini yo'qotadi. Shuning uchun bekor qilish ikki joyda:
HTMX'da kartaning o'rnida, JavaScript'siz esa «So'nggi qarorlar»
bo'limida.

⚠️ Kontent `oldingi_holat` ga qaytariladi, `VISIBLE` ga **emas**: post
yashirilishidan oldin allaqachon `PENDING` da turgan bo'lishi mumkin va
uni jimgina ko'rinadigan qilib yuborish tekshiruvni chetlab o'tardi.

⚠️ `Report.yopgan_chora` FK bor, chunki bekor qilish **aynan o'sha chora
yopgan** shikoyatlarni ochishi kerak — vaqt bo'yicha taxmin («bir xil
soniyada yopilganlar») bitta obyektga ketma-ket ikki marta chora
ko'rilganda buzilardi.

---

### ⚠️ Anonim post moderatorga anonim EMAS

Navbat haqiqiy muallifni ko'rsatadi (`selectors.Holat.muallif`), chunki
takroriy qoidabuzarni tanish kerak — D2-T11 (uch ogohlantirish) shunga
tayanadi va anonim post ortiga yashiringan odam aks holda cheksiz davom
etardi.

Anonimlik guard'i (`test_anonimlik.py`) shablonlarda xom `.author` ni
taqiqlaydi va **bu to'g'ri**: istisno qarori kodda, izoh bilan turadi —
shablonga sochilmaydi. **D2-T10 (maxfiylik siyosati) buni ochiq yozishi
shart.**

---

### ⚠️ Shikoyat eskalatsiyasi kontentni YASHIRMAYDI (D2-T1)

Uchta shikoyat postni **navbat boshiga** ko'taradi, lekin uni
ko'rinmas qilmaydi. Bu ataylab.

Dard.uz'da odamlar eng og'ir shaxsiy holatlarini yozadi. Agar kelishib
olgan uch kishi istalgan postni o'chirib tashlay olsa, mexanizm qurolga
aylanadi — va zarba aynan eng himoyasiz foydalanuvchiga tegadi.
Shoshilinch olib tashlash moderator qo'lida qoladi (D2-T2).

Foydalanuvchiga chegara soni ham **aytilmaydi**: «yana 2 ta shikoyat
kerak» degan xabar odamlarni kelishib shikoyat qilishga undardi.

---

### ⚠️ Flash xabarlar (`messages`)

`base.html` `components/_messages.html` ni include qiladi. **Buni olib
tashlamang** — u qo'shilgunicha (D2-T1) kodda 6 ta `messages.success()`
chaqiruvi bor edi va **hammasi jimgina yo'qolardi**: foydalanuvchi
«Dardingiz e'lon qilindi» tasdig'ini hech qachon ko'rmagan.

Xatoni topish qiyin bo'lgani bejiz emas: `INSTALLED_APPS`, middleware va
`messages` kontekst-protsessori boshidanoq to'g'ri sozlangan edi,
`response.context["messages"]` ham to'lardi. Uzilgan yagona halqa — HTML.

Shu sababli guard **render qilingan HTML** ni tekshiradi, sozlamani emas:
`apps/common/tests/test_templates.py::XabarlarTests`.

Xabar **toast emas, statik blok** (`role="status"`) — yuborilgandan
keyingi tasdiq oqimning bir qismi va JavaScript yuklanmasa ham
ko'rinishi kerak.

---

### ⚠️ Yechim ko'rinishi ota-postga bog'liq (D2-T1)

`Solution.objects.visible()` yechimning **o'z** holatini ham, **ota-post**
ochiqligini ham tekshiradi (`apps/solutions/models.py::SolutionQuerySet`).

Usiz: muammo yashirilsa, undagi yechimlarning `moderation_status` i
`VISIBLE` bo'lib qolaveradi va yechim `pk` bo'yicha to'g'ridan-to'g'ri
ochiladi. Bu D1-T5 dan beri mavjud edi va faqat D2-T1 birinchi ommaviy
`/shikoyat/yechim/<pk>/` manzilini qo'shganda D2-T3 guard'i ushladi.

**Istisno:** `complaint_detail` `ozi_korinadigan()` ishlatadi — muallif
o'z yashirilgan postini ko'radi, va u yerda `visible()` javoblarni
butunlay yo'qotib yuborardi.

---

### ⚠️ Tailwind build'i shablonlardan orqada qolmasin (D2-T1)

Tailwind sinflarni **shablonlarni skaner qilib** yaratadi. Yangi sinf
yozilib `npm run build` ishlatilmasa, u CSS'ga umuman tushmaydi va
**hech qanday xato bermaydi** — sahifa ochiladi, HTML'da sinf turadi,
testlar yashil, faqat uslub yo'q.

Buni `apps/common/tests/test_statik.py::TailwindBuildTests` tekshiradi:
shablonlardagi har bir sinf qurilgan CSS'da borligi shart.

CSS endi **uch joyda** quriladi va uchalasi ham shu commitdagi
shablonlarga mos bo'ladi:

| Joy | Qadam |
|---|---|
| Lokal | `npm run build` |
| CI | `Tailwind CSS` qadami (`npm ci && npm run build`) |
| Docker | `css` bosqichi (`node:22`), natija `runtime` ga ko'chiriladi |

⚠️ Docker'da `COPY --from=css ...` **`COPY . .` dan keyin** turishi shart,
aks holda kontekstdagi eski (yoki mavjud bo'lmagan) fayl qurilgan CSS ni
qayta yozib yuboradi.

---

### ⚠️ Ko'rinish invarianti (D2-T3)

Yashirilgan kontent hech qaysi ommaviy yo'lda chiqmasligi kerak. Qoida
`apps/common/tests/test_korinish_invarianti.py` da **ikki qatlamda**
majburlanadi:

1. **Ish vaqtida** — URLconf'dagi *barcha* yo'llar avtomatik aylanadi.
   Yangi ko'rinish (sitemap, RSS, API) qo'shilsa u **avtomatik**
   qamrab olinadi; ro'yxatni yangilash shart emas.
2. **Manba kodida** — `Complaint.objects` / `Solution.objects`
   `visible()` siz ishlatilgan joy topiladi (AST bo'yicha).

Ataylab qilingan istisnoga izoh **majburiy**:

```python
# korinish-istisno: sanoqchini yangilash, kontent ko'rsatish emas.
Complaint.all_objects.filter(pk=muammo.pk).update(...)
```

Istisno taqiqlanmaydi — u **ko'rinadigan va izohlangan** bo'lishi kerak.

**D0-T10 qisman:** barcha fayllar tayyor va lokal repetitsiyada tekshirilgan;
server hali olinmagan. Ketma-ketlik: [`DEPLOY.md`](DEPLOY.md).

**M2 — xavfsizlik va moderatsiya: kod bo'yicha tugadi.** Reja uni ommaviy
ishga tushirishdan **OLDIN majburiy** deb belgilagan va o'n bir taskning
hammasi yozildi. Ikkitasining ochiq qismi koddan tashqarida:

- **D2-T6** — rasmiy ishonch telefoni topilishi kerak (hozir `ISHONCH_TELEFONI = None`,
  103/112 ko'rsatiladi). Egasining shaxsiy raqami tashkilot liniyasi emas.
- **D2-T10** — matnlarni yurist ko'rishi kerak (`HUQUQIY_KORILDI = False`,
  har sahifada ochiq belgi turadi).

Keyingi: **M4 — qidiruv va SEO** (PostgreSQL FTS, lotin/kiril
normalizatsiyasi, slug URL, sitemap, Schema.org).

### So'rov sonlari (D1-T14 da o'lchangan)

| Sahifa | Mehmon | Kirgan |
|---|---|---|
| Lenta (20 karta) | 2 | 7 |
| Lenta, 2-sahifa | — | 8 |
| Batafsil (15 yechim) | 3 | 9 |
| Saqlanganlar | — | 4 |

Sonlar **element soniga bog'liq emas** — `test_n_plus_1.py` buni
qotirgan (5 va 50 element bir xil son berishi shart).

⚠️ Kirgan foydalanuvchida **D2-T11 da bittadan so'rov qo'shildi**
(bloklangan mualliflar ro'yxati) va bu **ongli** qaror. Ro'yxat bir
marta olinadi va so'rovga **qiymat** sifatida tushadi — ichma-ich
`QuerySet` bo'lsa PostgreSQL uni har sahifada qayta bajarardi.
Cheklov banneri esa so'rov **qo'shmaydi**: u `request.user` dagi
maydonlarni o'qiydi.

### ⚠️ Telegram login uchun sozlash

```bash
# 1) @BotFather da bot yarating
# 2) /setdomain bilan domenni bog'lang (dev uchun ham shart)
# 3) .env ga yozing:
TELEGRAM_BOT_TOKEN=123456:AAH...
TELEGRAM_BOT_USERNAME=dard_uz_bot
```

Bot sozlanmagan bo'lsa kirish sahifasi buni **ochiq aytadi** va tugma
ko'rsatilmaydi — bosilganda hech nima bo'lmaydigan tugma «sayt buzuq»
taassurotini qoldiradi.

⚠️ **D2-T9 (CSP) uchun:** `script-src` ga `https://telegram.org`,
`frame-src` ga `https://oauth.telegram.org` qo'shilishi **shart** —
aks holda kirish butunlay ishlamay qoladi va sabab faqat brauzer
konsolida qoladi.

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
