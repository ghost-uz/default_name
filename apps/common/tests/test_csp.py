"""Xavfsizlik sarlavhalari va CSP (D2-T9)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.common.middleware import csp_sarlavhasi

pytestmark = pytest.mark.django_db

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"


def yonalish(javob, nom: str) -> list[str]:
    """Javobdagi CSP yo'nalishining manbalari."""
    for qism in javob["Content-Security-Policy"].split(";"):
        bolaklar = qism.strip().split()
        if bolaklar and bolaklar[0] == nom:
            return bolaklar[1:]
    return []


# ===========================================================================
# Sarlavha bor va nonce bilan bog'langan
# ===========================================================================
def test_CSP_sarlavhasi_har_javobda(client):
    javob = client.get("/")

    assert "Content-Security-Policy" in javob


def test_NONCE_sarlavhada_va_HTML_da_BIR_XIL(client):
    """⭐ Eng muhim bog'lanish.

    Sarlavhadagi nonce sahifadagi `<script nonce=...>` bilan mos
    kelmasa, BARCHA inline skript jimgina bloklanadi — mavzu skripti
    ishlamaydi, sahifa "chaqnaydi" va konsolda faqat CSP xatosi
    qoladi. Shuning uchun nonce va sarlavha BITTA middleware'da.
    """
    javob = client.get("/")
    matn = javob.content.decode()

    sarlavhadagi = re.search(
        r"'nonce-([^']+)'", javob["Content-Security-Policy"]
    ).group(1)
    htmldagi = re.findall(r'<script nonce="([^"]+)"', matn)

    assert htmldagi, "sahifada nonce'li skript yo'q"
    assert set(htmldagi) == {sarlavhadagi}


def test_NONCE_har_sorovda_YANGI(client):
    """Takrorlanuvchi nonce CSP'ni butunlay ma'nosiz qiladi."""
    birinchi = client.get("/")["Content-Security-Policy"]
    ikkinchi = client.get("/")["Content-Security-Policy"]

    assert birinchi != ikkinchi


# ===========================================================================
# ⚠️⚠️ Telegram — bu qatorlarsiz login BUTUNLAY buziladi
# ===========================================================================
def test_TELEGRAM_skripti_va_iframe_RUXSAT_etilgan(client):
    """⚠️⚠️ Vidjet `telegram.org` dan skript yuklaydi va ichkarida
    `oauth.telegram.org` iframe'ini ochadi.

    Ikkalasi ham CSP'da ochiq bo'lmasa, "Telegram orqali kirish"
    tugmasi UMUMAN CHIQMAYDI — sahifa esa xatosiz ko'rinadi va sabab
    faqat konsolda qoladi.
    """
    javob = client.get(reverse("login"))

    assert "https://telegram.org" in yonalish(javob, "script-src")
    assert "https://oauth.telegram.org" in yonalish(javob, "frame-src")


def test_login_sahifasida_telegram_skripti_BOR(client):
    """Sozlama va shablon bir-biridan uzilib qolmasin.

    ⚠️ Bot sozlanmagan bo'lsa vidjet UMUMAN chizilmaydi (shablonda
       shart bor) — shuning uchun test uni ochiq yoqadi. Aks holda
       test hech narsa tekshirmasdan "yashil" bo'lardi.
    """
    from django.test import override_settings

    with override_settings(
        TELEGRAM_BOT_TOKEN="123:sinov", TELEGRAM_BOT_USERNAME="sinov_bot"
    ):
        matn = client.get(reverse("login")).content.decode()

    assert "https://telegram.org/js/telegram-widget.js" in matn


# ===========================================================================
# Qat'iylik — bo'shashtirish JIM o'tmasin
# ===========================================================================
def test_script_src_da_UNSAFE_INLINE_YOQ(client):
    """⚠️ `'unsafe-inline'` qo'shilsa nonce mexanizmi ma'nosiz bo'ladi:
    brauzer nonce'ni umuman tekshirmaydi."""
    manbalar = yonalish(client.get("/"), "script-src")

    assert "'unsafe-inline'" not in manbalar
    assert "'unsafe-eval'" not in manbalar


def test_style_src_da_UNSAFE_INLINE_YOQ(client):
    """⚠️ D2-T9 da ikkita inline `style=` atributi olib tashlandi
    (stagger animatsiyasi va mobil nav) — aynan shu qatorni qat'iy
    qoldirish uchun."""
    assert "'unsafe-inline'" not in yonalish(client.get("/"), "style-src")


@pytest.mark.parametrize(
    ("nom", "kutilgan"),
    [
        ("frame-ancestors", "'none'"),
        ("object-src", "'none'"),
        ("base-uri", "'self'"),
        ("form-action", "'self'"),
        ("default-src", "'self'"),
    ],
)
def test_asosiy_yonalishlar(client, nom, kutilgan):
    assert kutilgan in yonalish(client.get("/"), nom)


def test_shablonlarda_INLINE_STYLE_YOQ():
    """⭐ CSP qat'iyligini SAQLAB TURADIGAN guard.

    Bitta inline `style=` atributi qo'shilsa, u CSP'da jimgina
    bloklanadi: element chizilaveradi, faqat uslub qo'llanmaydi.
    Buni ko'z bilan payqash qiyin, chunki qolgan uslublar joyida.

    Muqobil: `style-src` ga `'unsafe-inline'` qo'shish — lekin u butun
    uslub himoyasini ochib qo'yadi (CSS orqali ma'lumot o'g'irlash
    haqiqiy usul). Shuning uchun taqiq shablon darajasida.
    """
    naqsh = re.compile(r'\sstyle\s*=\s*["\']')
    buzuqlar = []

    for yol in sorted(TEMPLATES_DIR.rglob("*.html")):
        matn = yol.read_text(encoding="utf-8")
        for m in naqsh.finditer(matn):
            # `{% comment %}` ichidagi misollar hisobga olinmasin.
            parcha = matn[max(0, m.start() - 500) : m.start()]
            if parcha.count("{% comment %}") > parcha.count("{% endcomment %}"):
                continue
            qator = matn[: m.start()].count("\n") + 1
            buzuqlar.append(f"{yol.relative_to(TEMPLATES_DIR)}:{qator}")

    assert buzuqlar == [], (
        "Shablonda inline `style=` topildi — CSP uni bloklaydi. "
        "Sinf ishlating (`tailwind/input.css`):\n  " + "\n  ".join(buzuqlar)
    )


# ===========================================================================
# Boshqa xavfsizlik sarlavhalari
# ===========================================================================
def test_PERMISSIONS_POLICY_sarlavhasi(client):
    javob = client.get("/")

    assert "camera=()" in javob["Permissions-Policy"]
    assert "microphone=()" in javob["Permissions-Policy"]


def test_X_FRAME_OPTIONS_DENY(client):
    assert client.get("/")["X-Frame-Options"] == "DENY"


def test_NOSNIFF_va_REFERRER(client):
    javob = client.get("/")

    assert javob["X-Content-Type-Options"] == "nosniff"
    # ⚠️ `same-origin` — `strict-origin-when-cross-origin` DAN QAT'IYROQ:
    #    begona saytga manzil UMUMAN yuborilmaydi. Bu yerda bu muhim,
    #    chunki post manzili odam nima o'qiganini oshkor qiladi.
    assert javob["Referrer-Policy"] == "same-origin"


def test_CSRF_cookie_HTTPONLY_EMAS():
    """⚠️ ATAYLAB `False` — HTMX tokenni JavaScript'dan o'qiydi
    (`hx-headers`, base.html). `True` qilinsa ovoz berish va boshqa
    HTMX so'rovlari 403 bilan yiqilardi."""
    assert settings.CSRF_COOKIE_HTTPONLY is False
    assert settings.SESSION_COOKIE_HTTPONLY is True


# ===========================================================================
# Sozlama bilan boshqarilishi
# ===========================================================================
def test_yonalishlar_SOZLAMADAN_olinadi():
    """Yangi tashqi resurs qo'shilganda middleware tegilmasin."""
    from django.test import override_settings

    with override_settings(CSP_YONALISHLARI={"img-src": ["https://cdn.misol"]}):
        sarlavha = csp_sarlavhasi("ABC")

    assert sarlavha == "img-src https://cdn.misol"


def test_nonce_FAQAT_script_src_ga_qoshiladi():
    """⚠️ `style-src` ga nonce qo'yish inline `<style>` bloklariga yo'l
    ochardi va hech qanday foyda bermasdi — bizda ular yo'q."""
    sarlavha = csp_sarlavhasi("ABC")

    assert "script-src 'nonce-ABC'" in sarlavha
    assert "style-src 'nonce-ABC'" not in sarlavha


def test_MAVJUD_sarlavha_qayta_yozilmaydi(rf):
    """Ko'rinish o'ziga xos siyosat qo'ygan bo'lsa, uni bosib ketish
    jim xato bo'lardi."""
    from django.http import HttpResponse

    from apps.common.middleware import CSPMiddleware

    def korinish(request):
        javob = HttpResponse("ok")
        javob["Content-Security-Policy"] = "default-src 'none'"
        return javob

    javob = CSPMiddleware(korinish)(rf.get("/"))

    assert javob["Content-Security-Policy"] == "default-src 'none'"


def test_HTMX_va_app_js_TASHQI_emas():
    """⚠️ `script-src 'self'` — vendorlangan fayllar shart.

    HTMX CDN'dan yuklansa CSP uni bloklardi va ovoz berish, sahifalash,
    moderatsiya navbati — hammasi jim ishlamay qolardi.
    """
    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert "js/vendor/htmx.min.js" in base
    assert "cdn." not in base
    assert (Path(settings.BASE_DIR) / "static/js/vendor/htmx.min.js").exists()


def test_sozlamalarda_TAKROR_YOQ():
    """⭐ D2-T9 DA HAQIQATAN YUZ BERGAN XATO.

    `config/settings/base.py` da xavfsizlik bo'limi allaqachon bor edi;
    D2-T9 da beshta sozlama IKKINCHI marta yozildi. Python'da oxirgi
    yozuv g'olib chiqadi — ya'ni yuqoridagi qiymat vakolatli ko'rinadi,
    amalda esa pastdagisi ishlaydi.

    Bu yerda u `SECURE_REFERRER_POLICY` ni "same-origin" dan
    "strict-origin-when-cross-origin" ga BO'SHASHTIRIB yuborardi — va
    hech narsa xato bermasdi.
    """
    import ast

    for nom in ("base.py", "dev.py", "prod.py", "test.py"):
        yol = Path(settings.BASE_DIR) / "config" / "settings" / nom
        daraxt = ast.parse(yol.read_text(encoding="utf-8"))

        korilgan: dict[str, int] = {}
        takrorlar = []
        for tugun in daraxt.body:
            if not isinstance(tugun, ast.Assign):
                continue
            for maqsad in tugun.targets:
                if not isinstance(maqsad, ast.Name) or not maqsad.id.isupper():
                    continue
                if maqsad.id in korilgan:
                    takrorlar.append(
                        f"{nom}:{tugun.lineno} {maqsad.id} "
                        f"(oldingisi {korilgan[maqsad.id]}-qatorda)"
                    )
                korilgan[maqsad.id] = tugun.lineno

        assert takrorlar == [], (
            "Sozlama ikki marta yozilgan — oxirgisi g'olib chiqadi va "
            "birinchisi chalg'ituvchi bo'lib qoladi:\n  " + "\n  ".join(takrorlar)
        )


def test_HTMX_inline_uslub_blokini_KIRITMAYDI(client):
    """⭐ JONLI BRAUZERDA TOPILGAN BUZILISH.

    HTMX standart holatda `<head>` ga inline `<style>` qo'shadi
    (`.htmx-indicator{opacity:0}` ...). CSP uni bloklaydi va HAR
    SAHIFA yuklanishida konsolda buzilish qoladi — sayt esa xatosiz
    ko'rinadi, ya'ni buni faqat konsolga qarab topish mumkin.

    Meta olib tashlansa, buzilish JIMGINA qaytadi. Shuning uchun
    guard uchta narsani birdan tekshiradi: meta, uslub sinflari va
    `style-src` ning qat'iyligi.
    """
    matn = client.get("/").content.decode()

    assert '"includeIndicatorStyles": false' in matn
    assert 'name="htmx-config"' in matn
    css = (Path(settings.BASE_DIR) / "static/css/app.css").read_text(encoding="utf-8")
    assert ".htmx-indicator" in css, (
        "HTMX indikatori uslubi CSS'da yo'q — `npm run build` qiling"
    )
