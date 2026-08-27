# 🚀 "Dard.uz" (Avlodlar) — Biznes va Texnik Arxitektura Hujjati

> **Hujjat tarixi**
> · v1 — asl reja (1-9 bo'limlar)
> · v2 (2026-08-24) — texnik tahlildan keyin to'ldirildi: **6.1** (yetishmayotgan
>   modellar), **9.1** (qayta tartiblangan yo'l xaritasi) va **10-18** bo'limlar
>   qo'shildi. Asl matn o'zgartirilmagan.
>
> Ishga oid batafsil vazifalar ro'yxati: **`def_tasks.json`** (66 ta task, 8 faza).
> Front-end beta maketi: **`frontend/`** (8 sahifa) + `frontend/design-system/MASTER.md`.

## 1. Loyiha Qisqacha Mazmuni (Executive Summary)
**Loyiha nomi:** Dard.uz (ishchi nom)
**Shior:** "Nolima, yechim topamiz!"
**Konsepsiya:** O'zbekiston aholisi uchun hayotiy muammolar (shikoyatlar) bilan o'rtoqlashish va ularga real tajribaga asoslangan yechimlar topish ijtimoiy platformasi. Muammolar avlodlar (Gen Z, Millennial, Boomer) kesimida ajratiladi va dolzarbligiga qarab reytinglanadi.

---

## 2. Bozor va Muammo (Market & Problem)
**Muammo:**
- Odamlarda psixologik, huquqiy, moliyaviy yoki shaxsiy munosabatlardagi muammolarini anonim va ochiq muhokama qilish uchun maxsus platforma yo'q.
- An'anaviy forumlar eskirgan, ijtimoiy tarmoq guruhlari esa tartibsiz va yoshlar (xususan Gen Z) uchun qulay emas.
- Maslahat yoki yechim izlaganlar kerakli mutaxassisni yoki shu muammoni boshidan kechirgan odamni tez topa olmaydi.

**Yechim:**
- Gamifikatsiya qilingan (upvote/downvote mexanikasi), zamonaviy UI/UX ga ega, asosan yoshlar va katta avlod vakillarining dardu-hasratlari hamda yechimlarini birlashtiruvchi markazlashgan, interaktiv maydon.

---

## 3. Maqsadli Auditoriya (Target Audience)
- **Foydalanuvchilar (B2C):** 16-45 yoshdagi, ijtimoiy tarmoqlarda faol, o'z muammosi bilan bo'lishishni yoki boshqalarga maslahat berishni xohlovchi insonlar.
- **Ekspertlar (B2B/Freelance):** Psixologlar, HR-mutaxassislar, yuristlar, rieltorlar, IT-mutaxassislar. Ular platformadan o'zlarining shaxsiy brendini rivojlantirish va potensial mijoz topish uchun foydalanadilar.

---

## 4. Monetizatsiya Modeli (Business Model)
Platforma dastlabki bosqichda 100% bepul ishlaydi, foydalanuvchilar bazasi (Community) shakllangach, quyidagi modellar ishga tushadi:
1. **"PRO Ekspert" obunasi (SaaS B2B):** Mutaxassislar o'z profillariga "To'g'ridan-to'g'ri bog'lanish" tugmasini qo'shish, maxsus nishon (badge) olish va yechimlari doim yuqorida turishi uchun oylik to'lov qilishadi (Click/Payme orqali).
2. **Boost (Topga olib chiqish):** Shoshilinch muammosi bor foydalanuvchilar o'z postini "Qaynoq (Trending)" ro'yxatning eng yuqorisida saqlab turish uchun mikro-to'lov amalga oshiradilar.
3. **Kontekstual Reklama:** Muammo toifasiga qarab yo'naltirilgan reklama (masalan: "Ta'lim" muammolari sahifasida o'quv markazlari, "Uy-joy" sahifasida developerlar reklamasi).

---

## 5. Texnik Arxitektura (Tech Stack)
Loyiha tezkorlik, SEO va qulaylikni ta'minlash uchun quyidagi zamonaviy va sinovdan o'tgan texnologiyalar ustiga quriladi:
- **Backend:** Python + Django (Ishonchli, kengayishga moyil va xavfsiz).
- **Frontend:** Django Templates + Tailwind CSS (Moslashuvchan va chiroyli dizayn) + HTMX (SPA kabi tezkor ishlash, sahifani yangilamasdan reyting berish va post yuklash uchun).
- **Ma'lumotlar Bazasi:** PostgreSQL (Relatsion ma'lumotlar, katta hajmdagi ovozlar va qidiruv uchun).
- **Kesh va Asinxron jarayonlar:** Redis + Celery (Trending postlarni fonda hisoblash, Telegram botga bildirishnomalar yuborish).
- **Autentifikatsiya:** Telegram Web Login (Foydalanuvchilar 1 klikda, qo'shimcha parollarsiz ro'yxatdan o'tishi uchun).
- **Infratuzilma (Deploy):** Docker va Docker Compose orqali konteynerizatsiya, Nginx va Gunicorn kombinatsiyasida Linux VPS (DigitalOcean kabi) serverlarida joylashtirish.

---

## 6. Ma'lumotlar Bazasi Strukturasi (Database Schema)
Asosiy modellar va ularning aloqalari:
- **User (Foydalanuvchi):** `id`, `username`, `telegram_id`, `karma_points` (faolligi uchun), `is_expert`.
- **Category (Kategoriya):** `id`, `name` (Karyera, Munosabatlar, Moliya, O'qish...), `icon`, `slug`.
- **Complaint (Muammo/Shikoyat):** `id`, `author_id`, `category_id`, `title`, `description`, `generation_tag` (GenZ/Millennial/Boomer), `upvotes`, `is_anonymous`, `is_solved`, `created_at`.
- **Solution (Yechim):** `id`, `complaint_id`, `author_id`, `content`, `upvotes`, `is_accepted` (Muammo egasi qabul qilgani), `created_at`.

### 6.1 To'ldirilgan sxema (v2)

Yuqoridagi 4 ta model mahsulotning skeleti, lekin ular bilan ishga tushirib
bo'lmaydi. Quyidagilar **keyinroq qo'shib bo'lmaydigan** (yoki juda qimmatga
tushadigan) bo'shliqlar:

#### ⚠️ Vote — eng muhim yetishmovchilik

`upvotes` butun son sifatida saqlansa:
- bir odam cheksiz marta ovoz bera oladi;
- ovozni qaytarib olish imkoni yo'q;
- «men ovoz berganmanmi?» degan savolga javob yo'q (maketdagi bosilgan holat
  ishlamaydi);
- soxta ovozlarni topib tozalab bo'lmaydi.

```
Vote: id, user_id, target (complaint|solution), value (+1/-1), created_at
      UNIQUE(user_id, target)
```
`upvotes` maydoni saqlanadi, lekin **keshlangan sanoq** sifatida — `F()` ifodasi
bilan yangilanadi. Bu qaror MVP'dan keyin o'zgartirilmaydi: butun ovoz tarixini
qayta tiklab bo'lmaydi.

#### Complaint'ga qo'shiladigan maydonlar

| Maydon | Nega |
|---|---|
| `slug` | 5-bo'limda SEO asosiy sabab deb ko'rsatilgan, lekin `/muammo/123` SEO bermaydi |
| `hot_score` (indeksli) | «Qaynoq» saralashni har so'rovda hisoblash lentani sekinlashtiradi |
| `moderation_status` | Ko'rinish nazorati (13-bo'lim) |
| `views_count`, `solutions_count` | Denormalizatsiya — sanash so'rovlarini yo'q qiladi |
| `accepted_solution` (FK) | Qabul qilingan yechimga to'g'ridan-to'g'ri havola |
| `updated_at`, `deleted_at` | Tahrir tarixi va yumshoq o'chirish |

#### Karma: butun son emas, hodisalar jurnali

`User.karma_points` oddiy son bo'lsa — post o'chganda karma qaytmaydi, qoida
o'zgarsa qayta hisoblab bo'lmaydi, foydalanuvchi «nega menda 1340?» deb so'rasa
javob yo'q.

```
KarmaEvent: id, user_id, event_type, points, source (obyekt), created_at
User.karma_cached  ← SUM(KarmaEvent.points) dan denormalizatsiya
```

#### Yetishmayotgan boshqa modellar

| Model | Nega kerak | Faza |
|---|---|---|
| `Tag` | Teglar UI'da bor, modelda yo'q | M1 |
| `Report` | Moderatsiyaning kirish nuqtasi | **M2** |
| `ModerationAction` / `AuditLog` | Nizo va huquqiy so'rovda yagona dalil | **M2** |
| `SavedItem` | Xatcho'plar (maketda bor) | M1 |
| `Notification` | Telegram bloklansa zaxira kanal | M5 |
| `ExpertProfile` | `is_expert` boolean yetarli emas: soha, tajriba, tasdiqlash, PRO muddati | M3 |
| `Subscription`, `BoostOrder`, `Payment` | 4-bo'limdagi monetizatsiya | M6 |
| `Match` | 7-bo'lim 5-qadamdagi kontakt almashinuvi — modeli yo'q edi | M6 |
| `Badge` / `UserBadge` | 8-bo'limdagi gamifikatsiya | M3 |

---

## 7. Foydalanuvchi Oqimi (User Flow)
1. **Kirish:** Foydalanuvchi saytga kiradi, eng qaynoq muammolarni o'qiydi (ro'yxatdan o'tmasdan ham kontentni ko'rish mumkin).
2. **Harakat:** Layk bosish yoki o'z muammosini yozish uchun Telegram orqali 1 soniyada avtorizatsiyadan o'tadi.
3. **Yaratish:** O'z hayotiy tajribasidagi muammoni yozadi, kategoriya va avlod (generation) tagini tanlaydi. Xohlasa, shaxsiy hayotini sir tutish uchun "Anonim" formatni tanlaydi.
4. **Reaksiya:** Boshqalar bu muammoga yechim yozadi va boshqa foydalanuvchilar ham yechimlarni baholaydi (upvote/downvote).
5. **Match (Ulanish):** Muammo egasi eng ma'qul yechimni tanlab "Qabul qilish" (Accept) tugmasini bosadi. Tizim ikkala tomonga bir-birining kontaktini taqdim etadi yoki yopiq chatda gaplashishga ruxsat beradi.

---

## 8. Marketing va O'sish Strategiyasi (Go-to-Market)
- **User-Generated Content (UGC) orqali Virallik:** Saytdagi eng qiziqarli, achinarli yoki bahsli dardu-hasratlar va ularga berilgan o'tkir yechimlarni anonim tarzda skrinshot qilib yoki sun'iy intellekt orqali ovozlashtirib TikTok va Instagram Reels'ga chiqarish.
- **Telegram Bot Integratsiyasi:** Yangi va qaynoq muammolar avtomatik ravishda loyihaning rasmiy Telegram kanaliga kros-post qilinadi. Obunachilar postdagi havola orqali to'g'ridan-to'g'ri saytga o'tib muhokamada qatnashadi.
- **Gamifikatsiya va Tavsiya Tizimi:** Yaxshi yechim berganlarga virtual "Karma" berib boriladi. Profilida karmasi yuqori bo'lgan (masalan, eng zo'r maslahatchilar) foydalanuvchilar oylik reytingda g'olib bo'lishadi va loyiha tomonidan rag'batlantiriladi.

---

## 9. Rivojlanish Bosqichlari (Roadmap)
- **1-Bosqich (MVP - 3 hafta):** Django, PostgreSQL va HTMX orqali platformaning poydevorini ko'tarish. Asosiy modellar, muammo/yechim yozish, upvote bosish mexanikalarini ulash.
- **2-Bosqich (Gamifikatsiya va Beta-test - 2 hafta):** Telegram avtorizatsiyasini joriy qilish, UI/UX ni Tailwind CSS yordamida jilolash. Karma tizimini sozlash va birinchi sinov auditoriyasini jalb qilish.
- **3-Bosqich (Marketing va Integratsiya - 2 hafta):** Redis va Celery yordamida Telegram kanalga avto-post qilishni sozlash. Reels va TikTok orqali organik trafik olib kelish, faollikni oshirish.
- **4-Bosqich (Monetizatsiya va Mass-Scale):** Mutaxassislar uchun PRO akkaunt funksiyalarini yoqish, mahalliy to'lov tizimlarini ulash va loyihani to'laqonli biznesga aylantirish.

### 9.1 Qayta tartiblangan yo'l xaritasi (v2)

Yuqoridagi tartibda **bitta tarkibiy muammo** bor: moderatsiya hech qaysi
bosqichda yo'q. Anonim + shaxsiy dard + ochiq post — bu birinchi kundanoq
suiisteʼmol demakdir. Moderatsiyasiz ommaviy ishga tushirish texnik qarz emas,
**huquqiy va insoniy xavf**.

| Faza | Nom | Taxminiy | Izoh |
|---|---|---|---|
| **M0** | Poydevor | 1 hafta | Skelet, Docker, CI, **erta deploy** |
| **M1** | Yadro (MVP) | 3 hafta | Asl 1-bosqich + `Vote` modeli |
| **M2** | **Xavfsizlik va moderatsiya** | 2 hafta | ⚠️ **Ishga tushirishdan oldin MAJBURIY** |
| **M3** | Gamifikatsiya va profil | 1.5 hafta | Asl 2-bosqich |
| **M4** | Qidiruv va SEO | 1.5 hafta | 5-bo'limdagi SEO va'dasini bajaradi |
| **M5** | Telegram va bildirishnomalar | 1.5 hafta | Asl 3-bosqich |
| **M6** | Monetizatsiya | 2 hafta | Asl 4-bosqich |
| **M7** | Ishga tushirish va kuzatuv | 1 hafta | Zaxira, Sentry, **sovuq start** |

**Muddat haqida ochiq gap:** asl reja MVP uchun 3 hafta, jami ~7 hafta bergan.
Moderatsiya, to'lov integratsiyasi va bot ishlari hisobga olinmagan. Bir kishi
uchun realroq baho — **12-14 hafta**. Bu rejani yomon qilmaydi, lekin sanani
shu asosda eʼlon qilgan maʼqul.

**Ikki qadamli ishga tushirish tavsiya etiladi:**
1. **Yopiq beta** (M2 tugagach) — taklif bo'yicha 100-200 kishi, moderatsiya yuki
   boshqariladigan darajada;
2. **Ommaviy** (M4 va M7-T7 tugagach) — TikTok/Reels kampaniyasi shundan keyin.

Sababi oddiy: viral trafik bo'sh yoki moderatsiyasiz platformaga kelsa, u
foydalanuvchi olib kelmaydi — u **bir marta kelib, qaytmaydigan** odamlarni
olib keladi. Birinchi taassurotni ikkinchi marta yaratib bo'lmaydi.

---

## 10. Loyiha Strukturasi (Project Layout)

```
dard/
├── config/                      # loyiha darajasidagi sozlamalar
│   ├── settings/
│   │   ├── base.py              # umumiy
│   │   ├── dev.py               # DEBUG, console email
│   │   ├── prod.py              # xavfsizlik, sirlar muhitdan
│   │   └── test.py              # tez parol hasher, locmem
│   ├── urls.py
│   ├── celery.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/                        # domen bo'yicha ajratilgan ilovalar
│   ├── common/                  # abstrakt modellar, mixinlar, htmx yordamchilari
│   ├── accounts/                # User, Telegram login, UserSession
│   ├── complaints/              # Complaint, Category, Tag, Vote, SavedItem
│   ├── solutions/               # Solution, qabul qilish, Match
│   ├── moderation/              # Report, ModerationAction, AuditLog, filtrlar
│   ├── gamification/            # KarmaEvent, Badge, Leaderboard
│   ├── payments/                # Subscription, BoostOrder, Click/Payme
│   └── notifications/           # Notification, Telegram bot dispatch
│
├── templates/
│   ├── base.html
│   ├── components/              # _complaint_card.html, _vote.html, _empty_state.html
│   └── <app>/                   # ilova bo'yicha sahifalar
│
├── static/                      # css/app.css (qurilgan), js/, img/
├── tailwind/input.css           # ⭐ dizayn tizimi manbai
├── locale/                      # i18n (uz, ru — 3-bosqichda)
├── tests/                       # integratsiya va e2e testlar
├── scripts/                     # seed, backup, bir martalik vazifalar
├── docker/                      # nginx.conf, entrypoint.sh
├── requirements/                # base.txt, dev.txt, prod.txt
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── manage.py
```

**Nega domen bo'yicha, tur bo'yicha emas:** `models/`, `views/`, `forms/` deb
ajratish kichik loyihada tartibli ko'rinadi, lekin har bir o'zgarish 4 ta
katalogga tegishga majbur qiladi. Domen bo'yicha ajratishda «moderatsiyani
o'zgartirish» = bitta katalogda ishlash.

**Ikki muhim qoida:**
1. `apps/common` boshqa ilovalarga **bog'lanmaydi** — u eng quyi qatlam.
2. Ilovalar orasidagi bog'liqlik bir tomonlama bo'lsin (`solutions` →
   `complaints` mumkin, teskarisi yo'q). Aylanma import Django'da tez paydo
   bo'ladi va uni keyin yechish qiyin.

---

## 11. Trending ("Qaynoq") Algoritmi

9-bosqichda «Celery trending hisoblaydi» deyilgan, lekin formula ko'rsatilmagan.
Tavsiya — Hacker News uslubidagi vaqt bilan so'nuvchi reyting:

```
score = log10(max(|ovozlar|, 1)) + sign(ovozlar) × (yosh_sekundlarda / 45000)
```

- `log10` — 1000 ovozli post 100 ovozlisidan 10 barobar emas, biroz yuqori
  turadi. Aks holda bitta viral post lentani haftalab band qiladi.
- `45000` ≈ 12.5 soat — postning «yarim yemirilish» davri. Kichik jamoada bu
  qiymatni **kattaroq** qilish kerak (masalan 90000), aks holda lenta juda tez
  bo'shab qoladi.

**Amalga oshirish:** `hot_score` maydonida saqlanadi, indekslanadi, Celery beat
har 10 daqiqada **faqat oxirgi 7 kunlik** postlarni `bulk_update` bilan
yangilaydi. Butun bazani qayta hisoblash 10 ming postdan keyin serverni yotqizadi.

---

## 12. Qidiruv Strategiyasi

Savol-javob saytida qidiruv — ikkilamchi funksiya emas: takroriy savollarni
kamaytiradi va SEO'dan kelgan foydalanuvchini ushlab qoladi.

**Tanlov: PostgreSQL FTS** (`SearchVector` + GIN indeks) + `pg_trgm`.
Alohida qidiruv xizmati (Meilisearch) 100 ming postdan oshgandagina oqlanadi.

### 12.1 ⚠️ O'zbek tiliga xos ikki muammo

**1. Postgres'da o'zbek lug'ati yo'q.** `english` konfiguratsiyasi o'zbekcha
so'zlarni noto'g'ri kesadi. Yechim: `'simple'` konfiguratsiya + `unaccent` +
trigram o'xshashligi.

**2. Ikki alifbo va uch xil apostrof.** Foydalanuvchilar ham lotin, ham kirilda
yozadi; apostrofni `'`, `ʻ`, `` ` `` — uch xil belgi bilan qo'yadi.
Normalizatsiyasiz **«ko'chmas mulk»** va **«кўчмас мулк»** bir-birini topmaydi
va qidiruv buzuq deb qabul qilinadi.

Yechim: indekslashda ham, so'rovda ham bitta normal shaklga keltirish
(kiril→lotin transliteratsiya + apostrof variantlarini birlashtirish).

---

## 13. Xavfsizlik, Moderatsiya va Huquqiy Masalalar

Bu bo'lim asl rejada yo'q edi, lekin **ishga tushirish uchun majburiy**.

### 13.1 Moderatsiya
- `Report` modeli + shikoyat oqimi (maketda modal bor, orqasi yo'q)
- Staff uchun **navbat interfeysi** — Django admin bu ish uchun juda sekin
- `moderation_status` **bitta joyda** tekshiriladi (`visible()` manager).
  Bitta unutilgan so'rov — masalan `sitemap.xml` — yashirilgan kontentni
  Google'ga beradi
- **O'zgarmas audit jurnali**: kim, nima, qachon, nima sababdan

### 13.2 ⚠️ Inqirozli kontent

Odamlarni ruhiy og'riqlari bilan bo'lishishga chaqiradigan platforma o'z joniga
qasd va o'z-o'ziga zarar haqidagi postlarni **muqarrar** oladi. Bu ehtimol emas,
vaqt masalasi.

Siyosat oldindan tayyor bo'lsin:
1. Kalit so'z aniqlansa — post **jim o'chirilmaydi** (o'chirish odamni
   yakkalaydi va vaziyatni og'irlashtiradi), balki moderatsiya navbatining eng
   tepasiga chiqariladi;
2. Muallifga va o'quvchilarga **rasmiy ishonch telefoni** ma'lumoti ko'rsatiladi;
3. Moderator uchun yozma javob qo'llanmasi bo'ladi.

> **Raqam ataylab bu yerga yozilmagan.** O'zbekistondagi rasmiy ishonch telefoni
> raqamini vakolatli manbadan tasdiqlab qo'ying — noto'g'ri inqiroz raqami
> raqam umuman bo'lmaganidan xavfliroq.

### 13.3 Texnik himoya
- Tezlik cheklovi (post, yechim, ovoz, shikoyat) — Redis'da
- Spam evristikasi: honeypot, forma to'ldirish vaqti, havola soni.
  CAPTCHA **faqat shubhali holatda** — u foydalanuvchini qochiradi
- CSP (nonce bilan), HSTS, secure cookie'lar
- Telegram login `hash` **va** `auth_date` tekshiruvi (aks holda eski so'rovni
  qayta yuborish mumkin)

### 13.4 Huquqiy minimum
- Foydalanish shartlari, maxfiylik siyosati, **16+ yosh chegarasi**
- Hisobni o'chirish: shaxsiy ma'lumot tozalanadi, **kontent qoladi** va
  anonimlashtiriladi — aks holda bir odam ketganda 200 ta yechim ham yo'qoladi
- Ma'lumot eksporti (JSON, fon vazifasida)

---

## 14. Anonimlik: Tahdid Modeli

`is_anonymous` — bu funksiya emas, **va'da**. Bir marta buzilsa ishonch qaytmaydi.

`is_anonymous=True` bo'lganda muallif quyidagilarning **hech birida**
ko'rinmasligi kerak:

| Joy | Xavf |
|---|---|
| Template | To'g'ridan-to'g'ri chiqarish |
| Kontekst / JSON | Ortiqcha maydon |
| Ommaviy profil | «Dardlari» tabida chiqib qolishi |
| Telegram kanal posti | Avto-post muallifni qo'shib yuborishi |
| `sitemap` / RSS | Metama'lumotda oshkor bo'lishi |
| Admin ro'yxati | Kim ko'ra olishi hujjatlashtirilmagan |

**Amalga oshirish:** `public_author` xossasi — anonim bo'lsa `None` qaytaradi;
har bir ommaviy ko'rinish uchun **test**: javob matnida `author.username` yo'q.
Bu qoida faqat testda qotirilgani uchun ishonchli bo'ladi.

**Ochiq savol:** bir foydalanuvchining bir nechta anonim posti o'zaro
bog'lanmasligi kerakmi? Agar ha — har postga alohida `anon_handle` kerak.
Tavsiya: maydonni **hozir** bo'sh holda qo'shib qo'ying, keyin to'ldirish arzon.

---

## 15. Testlash, CI va Kuzatuv

**Testlash.** pytest-django + factory_boy. Eng muhim uch guruh:
1. **Ko'rinish invariantlari** — anonimlik, moderatsiya holati
2. **Ovoz butunligi** — takroriy ovoz, almashish, parallel yozish
3. **So'rov sanog'i** — lenta ≤8 so'rov (`assertNumQueries` bilan qotiriladi)

**CI.** GitHub Actions: lint (ruff/black) → mypy → test (postgres+redis) →
coverage. Yashil bo'lmasa merge yo'q. Yolg'iz ishlaganda CI — code review o'rnini
bosuvchi yagona narsa.

**Kuzatuv.** Sentry + tuzilgan loglar (so'rov ID bilan) + `/health/` endpoint.
⚠️ Anonim post matni Sentry'ga tushib qolmasligi uchun so'rov tanasi maskalanadi.

⚠️ **Celery jim to'xtasa sayt ishlayotgandek ko'rinadi**, lekin bildirishnomalar
va trending o'ladi. `health` tekshiruvi Celery beat oxirgi marta qachon
ishlaganini ham ko'rsatsin — bu eng ko'p uchraydigan «ko'rinmas» nosozlik.

**Zaxira.** Kunlik `pg_dump`, boshqa fizik joyda, shifrlangan. Va eng muhimi:
**tiklashni bir marta amalda sinab ko'ring**. Sinalmagan zaxira — zaxira emas,
umid.

---

## 16. Muvaffaqiyat Metrikalari

Asl rejada muvaffaqiyat raqamlari yo'q edi. Ularsiz «loyiha yaxshi ketyaptimi?»
degan savolga his-tuyg'u bilan javob beriladi.

| Metrika | Maqsad | Nega muhim |
|---|---|---|
| **24 soatda javob olgan muammolar ulushi** | ≥ 80% | ⭐ **Eng muhim ko'rsatkich.** Mahsulotning asosiy va'dasi shu. 70% dan pastga tushsa — boshqa hamma raqam yaxshi bo'lsa ham platforma o'la boshlagan |
| Birinchi yechimgacha o'rtacha vaqt | < 6 soat | Tez javob qaytib kelishni belgilaydi |
| Yechilgan (accepted) ulushi | ≥ 40% | Faollikni emas, **sifatni** o'lchaydi |
| D7 qaytish (retention) | ≥ 25% | Bir martalik tashrifchi jamoa qurmaydi |
| Ekspert javob darajasi | ≥ 60% | PRO monetizatsiyasi shunga bog'liq |
| Moderatsiyagacha o'rtacha vaqt | < 4 soat | Sekin moderatsiya = ochiq suiisteʼmol |

---

## 17. Sovuq Start Rejasi

8-bo'lim virallikni yaxshi yozgan, lekin **eng katta yiqilish sababini**
qoldirgan: bo'sh platforma.

Birinchi foydalanuvchi keladi → savol yozadi → **javob olmaydi** → qaytmaydi.
Va u bilan birga uning tanishlari ham kelmaydi.

**Ommaviy e'londan OLDIN bajarilishi shart:**
- 50-100 ta **real** muammo (tanishlar, o'z tajribangiz, forumlardan ruxsat
  bilan ko'chirilgan holatlar)
- Har bir kategoriyada kamida **1 faol ekspert** (jami 15-20 kishi)
- Birinchi **14 kun** davomida har bir savolga javob berilishi kafolati —
  «javobsizlar» navbati har kuni tozalanadi

Bu texnik emas, mahsulot vazifasi — lekin M7 fazasidagi eng muhim ish
(`def_tasks.json` → `D7-T7`).

---

## 18. Ochiq Qarorlar va Risklar

To'liq ro'yxat `def_tasks.json` faylida (`ochiq_qarorlar` va `risklar`).
Qisqacha:

**Qaror kutayotgan 4 masala**
1. `Vote` modeli: umumiy (ContentType) yoki alohida jadvallar? → *tavsiya:
   alohida jadvallar*
2. Anonim postlar o'zaro bog'lanmasligi kerakmi? → *tavsiya: hozircha yo'q,
   lekin maydonni qo'shib qo'ying*
3. Telegram yagona kirish usuli bo'lib qolsinmi? → *tavsiya: MVP'da ha, lekin
   autentifikatsiyani provayderdan mustaqil yozing*
4. Qidiruv: Postgres FTS yoki Meilisearch? → *tavsiya: Postgres FTS*

**Eng yuqori 3 risk**
1. **Sovuq start** (ehtimol: yuqori / taʼsir: kritik) → 17-bo'lim
2. **Moderatsiya yuki bir kishiga tushishi** (yuqori / yuqori) → avtomatik
   filtrlar + 2-3 ko'ngilli moderator
3. **Inqirozli kontent** (o'rta / kritik) → 13.2-bo'lim, ishga tushirishdan
   oldin tayyor bo'lsin
