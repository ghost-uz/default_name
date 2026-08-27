# Dard.uz — Front-end maketi (beta)

Backend hali yozilmagan. Bu **statik, ishlaydigan maket** — dizayn tizimi va
barcha asosiy ekranlar. Django ulanganda shu fayllar to'g'ridan-to'g'ri
`templates/` ga ko'chadi.

---

## Ishga tushirish

```bash
cd frontend

# 1. Bog'liqliklar (bir marta)
npm install

# 2. CSS ni qurish
npm run build          # bir martalik, minified
npm run dev            # --watch rejimi (tahrirlash paytida)

# 3. Ko'rish — file:// EMAS, server orqali
python -m http.server 8077
#  -> http://127.0.0.1:8077/templates/landing.html
```

> `file://` orqali ochsangiz brauzer nisbiy `../static/` yo'llarini bloklashi
> mumkin. Har doim HTTP server orqali oching.

---

## Sahifalar

| Fayl | Nima | Nimani ko'rsatadi |
|---|---|---|
| `landing.html` | Marketing sahifasi | Hero, kategoriyalar, 4 qadam, jonli kontent, PRO, footer |
| `index.html` | **Lenta** (asosiy ekran) | 3 ustunli layout, saralash, avlod filtri, ovoz berish, skeleton |
| `complaint.html` | Muammo + yechimlar | Qabul qilingan yechim, ekspert javobi, yechim yozish, shikoyat modali |
| `create.html` | Yangi dard yozish | Validatsiya, belgi hisoblagich, anonim toggle, Boost, jonli ko'rinish |
| `categories.html` | Kategoriyalar | Bento to'r, bo'sh holat namunasi |
| `experts.html` | Ekspertlar katalogi | PRO va oddiy ekspert farqi, obuna narxi |
| `profile.html` | Foydalanuvchi profili | Karma, yutuqlar, klaviatura bilan boshqariladigan tablar, bo'sh holat |
| `login.html` | Kirish | Telegram Login (widget o'rni) |

**Ko'rish tartibi:** `landing.html` → `index.html` → `complaint.html` → `create.html`

---

## Tuzilma

```
frontend/
├── templates/           # sahifalar — Django templates/ ga aynan ko'chadi
├── static/
│   ├── css/app.css      # QURILGAN fayl — QO'LDA TAHRIRLAMANG
│   └── js/app.js        # maket interaktivligi (Django+HTMX da qisqaradi)
├── tailwind/input.css   # ⭐ DIZAYN TIZIMI MANBAI — o'zgartirishlar shu yerda
├── design-system/
│   └── MASTER.md        # qarorlar, tokenlar, qoidalar
└── package.json
```

**Muhim:** rang yoki o'lchamni o'zgartirish kerak bo'lsa — `tailwind/input.css`
ichidagi `:root` / `.dark` bloklarini tahrirlang, keyin `npm run build`.
`static/css/app.css` generatsiya qilinadi, unga qo'l tegizilmaydi.

---

## Nima ishlaydi (maketda)

- Ovoz berish — optimistik UI, holat `aria-pressed` da, «pop» animatsiyasi
- Yechimni qabul qilish — bittasi tanlanadi, boshqasi bekor bo'ladi
- Yorug'/qorong'i rejim — `localStorage`, FOUC yo'q
- Forma validatsiyasi — `blur` da tekshiradi, birinchi xato maydonga fokus
- Tablar — `←` `→` `Home` `End` tugmalari bilan
- Modal — `Escape`, fokus tuzog'i, fon bosilganda yopiladi
- Toast — 3.2s, `aria-live`, fokusni o'g'irlamaydi
- Mobil drawer, skeleton yuklanish, jonli sarlavha ko'rinishi

## Nima ishlamaydi (ataylab)

- Haqiqiy autentifikatsiya, ma'lumot saqlash, qidiruv, sahifalash
- To'lov (Boost / PRO) — tugmalar toast chiqaradi
- Kategoriya va filtr havolalari bir xil demo lentaga olib boradi

---

## Django'ga ko'chirish

Batafsil xarita: `design-system/MASTER.md` → 8-bo'lim.

Qisqacha:
1. `templates/*.html` dan takrorlanuvchi header/footer ni `base.html` ga ajrating
2. Kartani `components/_complaint_card.html` ga chiqaring
3. `data-vote`, `data-load-more`, `form[data-validate]` ni `hx-*` bilan almashtiring
4. Inline `<script>` larga `{% csp_nonce %}` qo'shing
5. `app.js` dan 3, 5, 7-bloklarni o'chiring (serverga o'tadi)

---

## Mehmon (kirmagan) foydalanuvchi ovoz berganda

**Tanlangan yo'l: C** — ovoz to'xtatiladi, tugma yonida login taklifi chiqadi.

```
?guest=1  -> mehmon rejimi
(parametrsiz) -> kirgan foydalanuvchi
```

Masalan: `http://127.0.0.1:8077/templates/index.html?guest=1`

**Xulq:**
- Ovoz **hisoblanmaydi** — hisoblagich ham, `aria-pressed` ham o'zgarmaydi
- Tugma ostida popover: «Ovoz berish uchun kiring / Bir odam — bir ovoz.
  O'qish uchun kirish shart emas» + Telegram tugmasi
- Yopiladi: tashqariga bosish, `Escape` (fokus tugmaga qaytadi), skroll,
  boshqa ovoz tugmasi, `×` tugmasi
- Bir vaqtda faqat bitta popover ochiq bo'ladi

**Nega A yoki B emas:**
- **A** (darhol login sahifasiga) — odam lentadan uziladi, qaysi postga ovoz
  bermoqchi bo'lganini yo'qotadi
- **B** (ovozni ko'rsatib, keyin qo'llash) — kirmasa, ko'rsatilgan ovoz yolg'on
  bo'lib chiqadi. Dard.uz'da ishonch asosiy valyuta

**Django'ga o'tganda:** `IS_GUEST` o'rniga
`{{ request.user.is_authenticated|yesno:"false,true" }}`, qolgan mantiq o'zgarmaydi.

> Bu qoida hozircha **faqat ovoz berishga** qo'llangan. Saqlash, yechim yozish
> va qabul qilish uchun ham kerak bo'lsa — `showLoginHint(anchor, sarlavha, matn)`
> funksiyasi umumiy qilib yozilgan, shunchaki chaqiring.
