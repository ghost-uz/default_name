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

Keyingi: **M3 — gamifikatsiya va profil** (karma ledgeri D3-T1 qisman
tayyor, keyin nishonlar, reyting, profil sahifasi, ekspert oqimi).

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
