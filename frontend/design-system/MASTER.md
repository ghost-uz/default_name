# Dard.uz — Dizayn tizimi (MASTER)

> Versiya 0.1 · beta maket · 2026-08-24
> Bu fayl **yagona haqiqat manbai**. Har qanday yangi sahifa avval shu hujjatga
> qarab quriladi. Chetga chiqish kerak bo'lsa — `pages/<sahifa>.md` yaratiladi
> va faqat o'sha sahifa uchun ustunlik qiladi.

---

## 1. Uslub qarori va uning sababi

| | |
|---|---|
| **Tanlangan uslub** | Minimal & Direct + Card/Bento gibridi |
| **Bir jumlada** | Ierarxiya **chegara (border) va bo'shliq** orqali quriladi — soya va gradient orqali emas. |
| **Referens** | Linear, Vercel, Threads — 2026-yilning eng keng tarqalgan minimalizm maktabi |

### Nega avtomatik tavsiya RAD ETILDI

`ui-ux-pro-max` bazasi so'rov bo'yicha **"Exaggerated Minimalism"** ni taklif qildi
(`font-size: clamp(3rem…12rem)`, `font-weight: 900`, ulkan bo'shliq).

Bu **rad etildi**, sabab: u fashion/portfolio/agentlik sahifalari uchun mo'ljallangan,
ya'ni **kontent zichligi past** joylar uchun. Dard.uz esa lentasida 30+ karta
ko'rsatadi — 10vw sarlavha bilan foydalanuvchi ekranda 1.5 ta post ko'radi va
skanerlash imkonsiz bo'ladi.

**Lekin butunlay tashlanmadi:** katta tipografiya `landing.html` da ishlatildi —
u yerda kontent zichligi past va e'tibor tortish maqsad. Ya'ni uslub *kerakli
joyda* qo'llanildi.

### Qat'iy taqiqlar

- ❌ Emoji ikonka sifatida (faqat inline SVG — Lucide uslubidagi 24×24, stroke 2)
- ❌ Kartalarda soya (`box-shadow`) — faqat modal va toast'da
- ❌ Gradient fon
- ❌ Komponentda xom HEX (`#2563EB`) — faqat semantik token
- ❌ Faqat rang orqali ma'no berish (har doim ikonka yoki matn qo'shiladi)

---

## 2. Ranglar

### Nega aynan shu palitra

Palitra `Q&A Community Platform` dan olindi va **ma'lumotlar bazasi modeliga
biriktirildi** — ya'ni rang bezak emas, holat tashuvchisi:

| Model maydoni | Rang | Ma'nosi |
|---|---|---|
| `upvotes` (musbat) | Yashil `--c-upvote` | Foydali |
| `Solution.is_accepted` / `is_solved` | Yashil `--c-solved` | Muammo yopilgan |
| `User.karma_points`, `is_expert`, Boost | Amber `--c-karma` | Reputatsiya / pullik |
| Asosiy harakat, havola | Ko'k `--c-primary` | Bosiladigan |
| Shikoyat, o'chirish, xato | Qizil `--c-danger` | Xavfli / xato |

### Semantik tokenlar

Komponentlar **faqat** shu nomlarni ishlatadi. Tailwind utility nomi qavsda.

| Token | Yorug' | Qorong'i | Utility |
|---|---|---|---|
| `--c-bg` | `#F8FAFC` | `#0B1220` | `bg-bg` |
| `--c-surface` | `#FFFFFF` | `#111A2C` | `bg-surface` |
| `--c-surface-2` | `#F1F5F9` | `#17223A` | `bg-surface-2` |
| `--c-fg` | `#0F172A` | `#E8EDF5` | `text-fg` |
| `--c-fg-muted` | `#64748B` | `#94A3B8` | `text-fg-muted` |
| `--c-border` | `#E2E8F0` | `#1F2C45` | `border-line` |
| `--c-border-strong` | `#CBD5E1` | `#2C3D5C` | `border-line-strong` |
| `--c-primary` | `#2563EB` | `#60A5FA` | `bg-primary` / `text-primary` |
| `--c-on-primary` | `#FFFFFF` | `#0B1220` | `text-on-primary` |
| `--c-karma` (matn) | `#B45309` | `#FBBF24` | `text-karma` |
| `--c-karma-icon` | `#D97706` | `#FBBF24` | `text-karma-icon` |
| `--c-solved` (matn) | `#15803D` | `#4ADE80` | `text-solved` |
| `--c-solved-icon` | `#16A34A` | `#4ADE80` | `text-solved-icon` |
| `--c-danger` | `#DC2626` | `#F87171` | `text-danger` |
| `--c-telegram` | `#229ED9` | `#229ED9` | `bg-telegram` |

> ⚠️ **`karma` va `karma-icon` nega ikkita?**
> `#D97706` oq fonda **3.03:1** — matn uchun WCAG AA dan (4.5:1) past.
> Shuning uchun **matn** `#B45309` (4.6:1), **ikonka va chegara** `#D97706`
> (3:1 yetarli). `solved` uchun ham xuddi shunday. Bu ataylab qilingan —
> bitta rangni ikki joyga ishlatmang.

### Avlod (`generation_tag`) ranglari

| Avlod | Matn | Fon | Utility |
|---|---|---|---|
| Gen Z | `#7C3AED` | `#F5F3FF` | `badge-genz` |
| Millennial | `#0E7490` | `#ECFEFF` | `badge-mil` |
| Boomer | `#B45309` | `#FEF3C7` | `badge-boom` |

Rang **hech qachon yolg'iz** ishlatilmaydi — badge'da doim matn bor.

---

## 3. Tipografika

**Bitta oila: Inter.** Ikkinchi shrift qo'shilmadi — sabab: kontent zichligi
yuqori interfeysda ikki oila diqqatni bo'ladi, ierarxiya **og'irlik** bilan
quriladi.

| Rol | O'lcham | Og'irlik | Interval |
|---|---|---|---|
| Landing H1 | `clamp(2.25rem, 7vw, 4.5rem)` | 800 | `-0.035em` |
| Sahifa H1 | 28px (mobil 24) | 800 | `-0.02em` |
| Bo'lim H2 | 20px | 700 | `-0.02em` |
| Karta sarlavhasi | 17-18px | 700 | `-0.02em` |
| Asosiy matn | 16px | 400 | normal, `line-height 1.6` |
| Post matni (`.prose-body`) | 17px | 400 | `line-height 1.7`, `max-width: 68ch` |
| Ikkilamchi | 15px / 14px | 400 | — |
| Meta, izoh | 13px | 400/500 | — |
| Badge, yorliq | 11px | 600, `uppercase` | `tracking-wide` |

**Qoidalar**
- Mobil asosiy matn **hech qachon 16px dan kichik emas** (iOS auto-zoom oldini oladi)
- Uzun matn `max-width: 68ch` — 60-75 belgi o'qish oynasi
- Raqamlar ustunda (`ovoz`, `karma`) **`.tnum`** klassi majburiy —
  `font-variant-numeric: tabular-nums`, aks holda raqam o'zgarganda layout sakraydi

---

## 4. Bo'shliq va o'lcham

4/8px ritmi: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`

| Element | Qiymat |
|---|---|
| Karta radiusi | `14px` (`--radius-card`) |
| Tugma radiusi | `8px` (`--radius-btn`) |
| Input radiusi | `10px` (`--radius-input`) |
| Chip / badge | `999px` |
| Kartalar orasi | `12px` (`gap-3`) |
| Bo'limlar orasi | `24px` / `56px` (landing) |
| Kontent maksimal kengligi | lenta `1400px`, detal `1100px`, profil `1000px` |

### Breakpointlar

| Nom | Kenglik | Nima o'zgaradi |
|---|---|---|
| — | `< 640px` | 1 ustun; ovoz tugmalari 44px; pastki nav |
| `sm` | `≥ 640px` | Ovoz ustuni kartaning chapiga chiqadi, 36px ga siqiladi |
| `lg` | `≥ 1024px` | 2 ustun (lenta + yon panel); pastki nav yashiriladi, tepa nav chiqadi |
| `xl` | `≥ 1280px` | 3 ustun (kategoriya raili + lenta + yon panel) |

---

## 5. Komponentlar

| Klass | Vazifasi | Muhim jihat |
|---|---|---|
| `.btn` + `.btn-primary` / `.btn-ghost` / `.btn-outline` / `.btn-telegram` | Tugmalar | Barchasi `min-h-11 min-w-11` = 44px |
| `.btn-sm` | Ixcham tugma | Mobilda **baribir 44px**, faqat `sm:` dan 36px |
| `.card` / `.card-hover` | Konteyner | Soya YO'Q — `border-line`; hover'da `border-line-strong` |
| `.chip` / `.chip-active` | Filtr, teg | Vizual 26px, **bosish maydoni `::after` bilan 44px** |
| `.badge-*` | Holat yorlig'i | Bosilmaydi, `<span>` |
| `.vote-btn` | Ovoz berish | Mobil 44px, desktop 36px; holat `aria-pressed` da |
| `.input` / `.input-invalid` | Forma | `min-h-11`; xato `aria-invalid` bilan birga |
| `.login-hint` | Mehmon uchun login taklifi | `position: fixed` — `.card`dagi `overflow-hidden` kesib qo'ymasligi uchun |
| `.skeleton` | Yuklanish | >300ms operatsiyada ko'rsatiladi |
| `.prose-body` | Post matni | `68ch` cheklov |

---

## 6. Animatsiya

| Nima | Davomiylik | Easing |
|---|---|---|
| Rang / hover | 150-200ms | `transition-colors` |
| Element chiqishi (`animate-in`) | 260ms | `cubic-bezier(.22,1,.36,1)` |
| Ovoz «pop» | 220ms | shu easing |
| Ro'yxat stagger | element boshiga +40ms | `--i` o'zgaruvchisi orqali |

**Qoidalar**
- Faqat `transform` va `opacity` animatsiya qilinadi — `width`/`height`/`top` YO'Q (reflow)
- `prefers-reduced-motion: reduce` da hamma narsa `0.01ms` ga tushadi (base qatlamda)
- Animatsiya foydalanuvchini **kutdirmaydi** — UI har doim bosiladigan holatda

---

## 7. Kirish imkoniyati (a11y) — majburiy minimum

- [x] Har sahifada `.skip-link` (klaviatura foydalanuvchisi uchun)
- [x] `:focus-visible` ko'rinadigan halqa (2px `--c-ring`), sichqonchada ko'rinmaydi
- [x] Ikonkali tugmalarda `aria-label`
- [x] Ovoz tugmalarida `aria-pressed`, tablarda `role="tab"` + o'q tugmalari
- [x] Forma: `<label for>` majburiy, placeholder yorliq O'RNIGA emas
- [x] Xato `aria-invalid` + `role`li matn, birinchi xato maydonga fokus
- [x] Toast `aria-live="polite"` — fokusni **o'g'irlamaydi**
- [x] Barcha matn kontrasti ≥ 4.5:1 (yorug' VA qorong'i alohida tekshirilgan)
- [x] Modalda `Escape`, fokus tuzog'i, `data-modal-close`

---

## 8. Django'ga ko'chirish xaritasi

Maket Django strukturasini **ataylab takrorlaydi**, ya'ni ko'chirish mexanik:

| Maket | Django |
|---|---|
| `templates/*.html` header/footer | `base.html` + `{% block content %}` |
| Takrorlanuvchi karta | `components/_complaint_card.html` (`{% include %}`) |
| `data-vote` tugmasi | `hx-post="{% url 'vote' c.pk %}" hx-swap="outerHTML"` |
| `data-load-more` | `hx-get="?page={{ page.next }}" hx-swap="beforeend"` |
| `form[data-validate]` | `hx-post` + server-side `form.errors` |
| `<script>` inline (mavzu) | `{% csp_nonce %}` bilan nonce qo'shiladi |
| `../static/css/app.css` | `{% static 'css/app.css' %}` |
| Telegram tugmasi | Telegram Login Widget |

**Ko'chirishdan keyin `app.js` dan olib tashlanadigan bloklar:** 3 (ovoz),
5 (yana yuklash), 7 (forma yuborish) — ular serverga o'tadi. Qoladi:
1 (mavzu), 2 (drawer), 4 (toast), 6 (modal), 9 (tablar).

---

## 9. Yechilmagan / keyingi qadam

- Qidiruv natijalari sahifasi (`search.html`) hali yo'q
- Bildirishnomalar markazi yo'q (Telegram bot 3-bosqichda)
- Yopiq chat (`Match` bosqichi) — faqat tugmasi bor, ekrani yo'q
- To'lov oqimi (Click/Payme) — 4-bosqich
- Mehmon cheklovi **faqat ovoz berishda**. Saqlash / yechim yozish / qabul
  qilish uchun ham `showLoginHint()` chaqirilishi kerak (funksiya umumiy)

---

## 10. Qaror jurnali

| Sana | Qaror | Sabab |
|---|---|---|
| 2026-08-24 | Uslub: Minimal & Direct + Card, «Exaggerated Minimalism» faqat landing'da | Lentada kontent zichligi yuqori — ulkan tipografiya skanerlashni buzadi |
| 2026-08-24 | `karma` / `karma-icon` ikkita alohida token | `#D97706` matn uchun 3.03:1 — WCAG AA dan past |
| 2026-08-24 | Barcha komponentlar bitta `@layer components` da, `@utility` ishlatilmaydi | v4'da `@utility` utilities qatlamiga tushib variantlarni bekor qiladi |
| 2026-08-24 | Mehmon ovozi: **C yo'li** (to'xtatish + popover) | A kontekstni yo'qotadi, B yolg'on tasdiq beradi |
| 2026-08-24 | Dev-server `scripts/serve.py` (`no-store`) | `python -m http.server` keshni buzmaydi — tahrir kirmagandek ko'rinadi |
