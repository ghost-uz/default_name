# syntax=docker/dockerfile:1
#
# Dard.uz — ko'p bosqichli (multi-stage) qurilish.
#
# Python 3.12: lokal .venv bilan AYNAN bir xil. Bu ataylab — konteyner va
# lokal muhit versiyasi farq qilsa, "menda ishlaydi" turkumidagi xatolar
# paydo bo'ladi va ularni topish qimmat.

# ---------------------------------------------------------------------------
# 1-bosqich: builder — kompilyatsiya vositalari FAQAT shu yerda qoladi
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Alohida virtual muhit — 2-bosqichga butunlay ko'chiriladi
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Faqat requirements ko'chiriladi: kod o'zgarganda bu qatlam KESHDAN olinadi
COPY requirements/ requirements/
ARG REQUIREMENTS=prod
RUN pip install --upgrade pip && pip install -r requirements/${REQUIREMENTS}.txt


# ---------------------------------------------------------------------------
# 2-bosqich: css — Tailwind chiqishi
#
# ⚠️ BU BOSQICH D2-T1 DA QO'SHILDI, CHUNKI OBRAZ STILSIZ CHIQARDI.
#
#    `static/css/app.css` — qurilish artefakti va `.gitignore` da. Lokalda
#    u mavjud bo'lgani uchun `COPY . .` uni olib kirardi va hamma narsa
#    joyida ko'rinardi. CI esa toza checkout qiladi: u yerda fayl YO'Q,
#    ya'ni GHCR ga ketayotgan obrazda BIRORTA HAM stil bo'lmasdi.
#
#    Xato hech qanday belgi bermasdi: obraz muvaffaqiyatli quriladi,
#    CI yashil, chunki obraz hech qachon ISHGA TUSHIRILMAYDI.
#
#    Endi CSS obraz ichida qayta quriladi — ya'ni u DOIM shu commitdagi
#    shablonlarga mos keladi.
# ---------------------------------------------------------------------------
FROM node:22-slim AS css

WORKDIR /css

# Lock-fayl bilan aynan qayta tiklanadigan o'rnatish. `--omit=dev` ISHLATILMAYDI:
# tailwindcss aynan devDependencies ichida.
COPY package.json package-lock.json ./
RUN npm ci

# `@source` ko'rsatgan kataloglar (tailwind/input.css ga qarang) — sinf
# nomlari shulardan skaner qilinadi.
COPY tailwind/ tailwind/
COPY templates/ templates/
COPY apps/ apps/
COPY static/ static/

RUN npm run build


# ---------------------------------------------------------------------------
# 3-bosqich: runtime — build-essential YO'Q, ~400 MB kichikroq
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# libpq5 — psycopg uchun ish vaqtidagi kutubxona (libpq-dev EMAS)
# curl — healthcheck uchun
RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# ⚠️ root'dan ishlamaymiz: konteyner buzilsa zarar cheklangan bo'lsin
RUN groupadd --system --gid 1001 dard \
    && useradd --system --uid 1001 --gid dard --create-home dard

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --chown=dard:dard docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY --chown=dard:dard . .

# ⚠️ `COPY . .` DAN KEYIN: aks holda kontekstdagi eski (yoki yo'q) fayl
#    qurilgan CSS ni qayta yozib yuborardi.
COPY --from=css --chown=dard:dard /css/static/css/app.css /app/static/css/app.css

# Statik va media uchun kataloglar (volume ulanmasa ham mavjud bo'lsin)
RUN mkdir -p /app/staticfiles /app/media && chown -R dard:dard /app

USER dard

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
