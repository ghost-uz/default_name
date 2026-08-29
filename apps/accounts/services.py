"""Foydalanuvchi bilan bog'liq biznes mantiq.

Model faqat ma'lumot va invariantlarni saqlaydi; qaror qabul qiladigan mantiq
shu yerda turadi — u testlanadigan va ko'rinishlardan mustaqil bo'lsin.
"""

from __future__ import annotations

import logging
import re
import secrets

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import User
from .validators import RESERVED_USERNAMES, USERNAME_RE, validate_username

log = logging.getLogger(__name__)


def username_bandmi(nom: str) -> bool:
    """Nom band yoki ishlatib bo'lmaydiganmi (registrga sezgir EMAS).

    ⚠️ ESKI NOMLAR HAM BAND. Nom o'zgartirilgandan keyin eskisi
       `oldingi_username` da qoladi va `/@eski/` yangisiga
       yo'naltiriladi. Uni boshqa odam olsa, eski havolalar o'sha
       odamga olib borardi — taqlid uchun tayyor mexanizm.
    """
    if not USERNAME_RE.match(nom) or nom.lower() in RESERVED_USERNAMES:
        return True
    return User.objects.filter(
        models.Q(username__iexact=nom) | models.Q(oldingi_username__iexact=nom)
    ).exists()


# ---------------------------------------------------------------------------
# Telegram'dan foydalanuvchi nomi (D1-T1)
# ---------------------------------------------------------------------------
# ⚠️ MAHSULOT QARORI: "avtomatik yasash + keyin BIR MARTA o'zgartirish"
#    (foydalanuvchi tanlovi, 2026-08-28).
#
#    Sabab: "Telegram orqali 1 soniyada kirish" va'dasi qo'shimcha ekran
#    (nom so'rash) bilan buziladi — ro'yxatdan o'tishning eng ko'p
#    tashlab ketiladigan qadami aynan shunday oynalar. Lekin avtomatik
#    nom ba'zan chiroyli chiqmaydi (kirillcha ism -> `dard_8f3a91`),
#    shuning uchun keyin bir marta tuzatish imkoni beriladi.
#
#    Cheksiz o'zgartirish RAD ETILDI: nom URL'da (`/@sardor92/`) va uni
#    tez-tez almashtirish taqlid hamda chalkashlik uchun eshik ochadi.
ZAXIRA_ASOS = "dard"
MIN_UZUNLIK = 3
MAX_UZUNLIK = 30


def _tasodifiy_quyruq(baytlar: int = 3) -> str:
    return secrets.token_hex(baytlar)


def _nomzod_tozalash(xom: str) -> str:
    """Istalgan matndan foydalanuvchi nomiga yaroqli asos yasaydi.

    ⚠️ `slugify` lotin bo'lmagan belgilarni TASHLAB YUBORADI: kirillcha
       yoki emoji ismdan bo'sh satr qoladi. Bu xato emas — chaqiruvchi
       zaxira asosga o'tadi.
    """
    asos = slugify(xom).replace("-", "_")
    asos = re.sub(r"[^a-z0-9_]", "", asos.lower())
    # Nom HARF bilan boshlanishi shart (validators.USERNAME_RE).
    asos = asos.lstrip("0123456789_")
    return asos[:MAX_UZUNLIK]


def telegramdan_username_yasash(telegram_data: dict) -> str:
    """Telegram ma'lumotidan Dard.uz foydalanuvchi nomini yasaydi.

    Tartib:
      1. Telegram `@username` — odam o'zi tanlagan, eng tanish variant.
      2. `first_name` dan yasalgan asos — lotin yozuvida bo'lsa ishlaydi.
      3. `dard_<tasodif>` — kirillcha/emoji ism yoki hammasi band bo'lsa.

    Har bosqichda nom band bo'lsa, oxiriga tasodifiy quyruq qo'shiladi.

    ⚠️ Bu funksiya "band emasligini" KAFOLATLAMAYDI — u faqat yaxshi
       nomzod beradi. Poyga holati (ikki parallel kirish bir xil nomni
       yasashi) chaqiruvchidagi `IntegrityError` sikli va bazadagi
       noyoblik cheklovi bilan yopiladi.
    """
    nomzodlar: list[str] = []

    telegram_nom = _nomzod_tozalash(telegram_data.get("username") or "")
    if len(telegram_nom) >= MIN_UZUNLIK:
        nomzodlar.append(telegram_nom)

    ismdan = _nomzod_tozalash(telegram_data.get("first_name") or "")
    if len(ismdan) >= MIN_UZUNLIK:
        nomzodlar.append(ismdan)

    for nomzod in nomzodlar:
        # ⚠️⚠️ "BAND" va "TAQIQLANGAN" — IKKI XIL HOLAT (jonli sinovda topildi).
        #
        #    Boshqa odam olgan nomga quyruq qo'shish to'g'ri:
        #        @demo -> demo_165260
        #
        #    Taqiqlangan nomga quyruq qo'shish esa `RESERVED_USERNAMES`
        #    ning butun MA'NOSINI yo'q qiladi — u taqlidga qarshi
        #    yozilgan:
        #        @ADMIN -> admin_62f95a     <- hamon "admin" bo'lib o'qiladi
        #        @moderator -> moderator_9f  <- hamon "moderator"
        #
        #    Shuning uchun taqiqlangan asosdan BUTUNLAY voz kechiladi va
        #    keyingi nomzodga (ism, keyin zaxira) o'tiladi.
        if nomzod.lower() in RESERVED_USERNAMES:
            continue

        if not username_bandmi(nomzod):
            return nomzod

        # Band bo'lsa — asosni saqlab, quyruq qo'shamiz.
        quyruqli = f"{nomzod[: MAX_UZUNLIK - 7]}_{_tasodifiy_quyruq()}"
        if not username_bandmi(quyruqli):
            return quyruqli

    # ⚠️ Oxirgi zaxira HAR DOIM yaroqli: `dard_` harf bilan boshlanadi va
    #    16 million variantdan biri. Bu yerga kirillcha ismli va
    #    Telegram username'siz foydalanuvchi tushadi.
    return f"{ZAXIRA_ASOS}_{_tasodifiy_quyruq()}"


@transaction.atomic
def usernameni_ozgartirish(*, user: User, yangi_nom: str) -> User:
    """Nomni BIR MARTA o'zgartiradi va eskisini band qilib qoldiradi.

    ⚠️ Interfeys (D3-T4 profil sozlamalari) hali yo'q — bu xizmat va
       model shu qaror bilan birga yozildi, chunki maydonlarni keyin
       qo'shish katta jadvalga migratsiya degani. Ko'rinish qo'shilganda
       u shu funksiyani chaqiradi.

    ⚠️ Eski nom O'CHIRILMAYDI, `oldingi_username` ga ko'chadi: `/@eski/`
       manzili yangisiga yo'naltirilishi kerak (301) va nomni boshqa
       odam olib, eski havolalarni o'ziga tortib ketmasligi shart.
    """
    if not user.nomni_ozgartira_oladimi:
        raise ValidationError("Nomni faqat bir marta o'zgartirish mumkin.")

    yangi_nom = (yangi_nom or "").strip()
    if yangi_nom.lower() == user.username.lower():
        raise ValidationError("Yangi nom eskisidan farq qilishi kerak.")
    validate_username(yangi_nom)
    if username_bandmi(yangi_nom):
        raise ValidationError("Bu foydalanuvchi nomi band.")

    user.oldingi_username = user.username
    user.username = yangi_nom
    user.username_ozgartirilgan = timezone.now()
    user.save(update_fields=["username", "oldingi_username", "username_ozgartirilgan"])
    return user


def username_boyicha_topish(nom: str) -> tuple[User | None, bool]:
    """`(user, yonaltirish_kerakmi)` — profil sahifasi uchun.

    Eski nom bilan kelingan bo'lsa `yonaltirish_kerakmi=True` qaytadi va
    ko'rinish 301 bilan yangi manzilga yuboradi.

    ⚠️ Ko'rinish tomoni D3-T4 (profil sahifasi) bilan birga ulanadi —
       hozir profil hali maketda. Funksiya shu yerda turadi, chunki u
       nom o'zgartirish qarorining ajralmas qismi: usiz eski havolalar
       jimgina 404 bo'lardi.
    """
    user = User.objects.filter(username__iexact=nom).first()
    if user is not None:
        return user, False

    eski = User.objects.filter(oldingi_username__iexact=nom).first()
    if eski is not None:
        return eski, True

    return None, False


@transaction.atomic
def telegram_foydalanuvchisini_olish_yoki_yaratish(
    telegram_data: dict,
) -> tuple[User, bool]:
    """Telegram ma'lumoti bo'yicha foydalanuvchini topadi yoki yaratadi.

    `(user, yangi_yaratildimi)` qaytaradi.

    ⚠️ FOYDALANUVCHI `telegram_id` BO'YICHA TOPILADI, nom bo'yicha EMAS.
       Telegram `@username` ni odam istalgan vaqtda o'zgartira oladi va
       uni BOSHQA ODAM olishi mumkin. Nom bo'yicha qidirilsa, eski nomni
       olgan begona odam sizning hisobingizga kirib qolardi.

    ⚠️ Poyga holati: ikki parallel so'rov bir xil nomni yasashi mumkin —
       shuning uchun yaratish `IntegrityError` ni ushlab qayta urinadi.
       DB cheklovi (Lower(username) unique) oxirgi himoya chizig'i.

    ⚠️ Mavjud foydalanuvchining ismi HAR KIRISHDA yangilanadi (Telegram'da
       o'zgargan bo'lishi mumkin), NOMI esa YO'Q: u bizniki va foydalanuvchi
       uni faqat o'zi o'zgartira oladi (`usernameni_ozgartirish`).
    """
    telegram_id = int(telegram_data["id"])
    ism = (telegram_data.get("first_name") or "")[:150]
    familiya = (telegram_data.get("last_name") or "")[:150]

    mavjud = User.objects.filter(telegram_id=telegram_id).first()
    if mavjud is not None:
        if (mavjud.first_name, mavjud.last_name) != (ism, familiya):
            mavjud.first_name = ism
            mavjud.last_name = familiya
            mavjud.save(update_fields=["first_name", "last_name"])
        return mavjud, False

    for _ in range(5):  # nom to'qnashuvida qayta urinish
        nom = telegramdan_username_yasash(telegram_data)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=nom,
                    telegram_id=telegram_id,
                    first_name=ism,
                    last_name=familiya,
                )
                # ⚠️ Parol ATAYLAB ishlatib bo'lmaydigan: bu hisobga faqat
                #    Telegram orqali kirish mumkin. Bo'sh parol qo'yilsa
                #    "parolni tiklash" oqimi orqali kirish yo'li ochilardi.
                user.set_unusable_password()
                user.save(update_fields=["password"])
                return user, True
        except IntegrityError:
            continue

    raise RuntimeError("Bo'sh foydalanuvchi nomi topilmadi (5 urinish)")


# ===========================================================================
# Hisobni o'chirish va ma'lumot eksporti (D2-T8)
# ===========================================================================
@transaction.atomic
def hisobni_ochirish(*, user) -> None:
    """Shaxsiy ma'lumotni tozalaydi, KONTENTNI QOLDIRADI.

    ⚠️⚠️ QABUL MEZONI: "o'chirilgan foydalanuvchining kontenti qoladi,
       ismi 'O'chirilgan foydalanuvchi'ga aylanadi".

       Sabab task tavsifida: foydalanuvchi o'chganda uning 200 ta
       yechimi ham o'chsa, bu BOSHQA ODAMLARNING qiymatini yo'q qiladi
       — ular savol berib, javob olgan edi.

    ⚠️ QATOR O'CHIRILMAYDI. `User.delete()` chaqirilsa `author` `NULL`
       bo'lardi va bitta muhokamadagi ikki xil odam bir xil
       "muallifsiz" ko'rinardi. Anonimlashtirish har hisobga o'z
       o'rindoshini qoldiradi.

    Tozalanadi:
      · `username` -> `ochirilgan_<hex>` (eski nom band bo'lib qolmaydi)
      · `telegram_id` -> `None` (qayta ro'yxatdan o'tish mumkin bo'lsin)
      · ism, bio, email
      · ovozlar va xatcho'plar (shaxsiy afzalliklar)
      · o'zi yozgan shikoyatlarda `reporter` -> `None`

    Qoladi:
      · dardlar va yechimlar (muallif — anonimlashtirilgan hisob)
      · karma tarixi (kontent hali turibdi, ballar ma'noli)
      · moderatsiya jurnali (D2-T7 — dalil, o'chirilmaydi)
    """
    from apps.complaints.models import ComplaintVote, SavedComplaint
    from apps.moderation.audit import audit
    from apps.moderation.models import AuditAction, Report
    from apps.solutions.models import SolutionVote

    if user.ochirilganmi:
        return

    eski_username = user.username

    # ⚠️ Ovoz va xatcho'p — SOF shaxsiy ma'lumot: ular odam nima
    #    o'qiganini va nimani ma'qullaganini ko'rsatadi. Kontentdan
    #    farqli, ularni saqlashning boshqalar uchun qiymati yo'q.
    #    Sanoqchilar `cast_vote()` orqali emas, to'g'ridan-to'g'ri
    #    o'chirilgani uchun biroz "yuqori" qoladi — bu ataylab: ovozni
    #    qaytarib olish reytingni qayta yozardi va boshqa odamlarning
    #    postlari tartibi o'zgarardi.
    ComplaintVote.objects.filter(user=user).delete()
    SolutionVote.objects.filter(user=user).delete()
    SavedComplaint.objects.filter(user=user).delete()

    # Shikoyat qoladi (moderator qarorining asosi), lekin kim yozgani
    # yo'qoladi — D2-T1 dagi `SET_NULL` bilan bir xil qaror.
    Report.objects.filter(reporter=user).update(reporter=None)

    user.username = f"ochirilgan_{secrets.token_hex(4)}"
    user.oldingi_username = ""
    user.telegram_id = None
    user.first_name = ""
    user.last_name = ""
    user.email = ""
    user.bio = ""
    user.is_active = False
    user.ochirilgan_at = timezone.now()
    user.save(
        update_fields=[
            "username",
            "oldingi_username",
            "telegram_id",
            "first_name",
            "last_name",
            "email",
            "bio",
            "is_active",
            "ochirilgan_at",
        ]
    )

    # ⚠️ Jurnalga ESKI nom yozilmaydi: aks holda anonimlashtirish
    #    ma'nosini yo'qotardi — jurnal ochiq bo'lgani uchun (D2-T7)
    #    eski nomni undan qayta topish mumkin bo'lardi.
    audit(
        action=AuditAction.HISOB_OCHIRILDI,
        obyekt=f"foydalanuvchi #{user.pk}",
        izoh="Foydalanuvchi o'z hisobini o'chirdi.",
    )
    log.info("Hisob o'chirildi: #%s (%s -> %s)", user.pk, eski_username, user.username)


def eksport_soralgan(*, user):
    """Eksport so'rovini yozadi va fon vazifasini navbatga qo'yadi.

    ⚠️ Bir vaqtda BITTA navbatdagi so'rov: tugmani bir necha marta
       bosgan odam o'nlab vazifa yaratib yubormasin.
    """
    from .models import EksportHolati, MalumotEksporti
    from .tasks import EKSPORT_MUDDATI, eksportni_tayyorlash

    mavjud = MalumotEksporti.objects.filter(
        user=user, holat=EksportHolati.NAVBATDA
    ).first()
    if mavjud is not None:
        return mavjud

    eksport = MalumotEksporti.objects.create(
        user=user, muddat=timezone.now() + EKSPORT_MUDDATI
    )
    # ⚠️ `on_commit` — vazifa TRANZAKSIYA YOPILGANDAN KEYIN yuborilsin.
    #    Aks holda worker qatorni hali ko'rmasligi mumkin va vazifa
    #    `DoesNotExist` bilan yiqilardi. Bu klassik poyga holati.
    transaction.on_commit(lambda: eksportni_tayyorlash.delay(eksport.pk))
    return eksport


@transaction.atomic
def rozilikni_yozish(*, user, yosh_tasdiqlandi: bool) -> None:
    """Rozilik sanasi va VERSIYASINI yozadi (D2-T10 qabul mezoni).

    ⚠️ VERSIYA HAM SAQLANADI. "Roziman" degan yozuv qaysi MATNGA
       tegishli ekani ma'lum bo'lmasa, jurnal hech narsa isbotlamaydi.

    ⚠️ Yosh tasdig'i ALOHIDA maydonda: u shartlarga rozilikdan boshqa
       narsa va "16+ ekanini tasdiqlaganmi?" degan savolga aniq javob
       kerak bo'ladi.
    """
    from django.conf import settings

    user.rozilik_at = timezone.now()
    user.rozilik_versiyasi = settings.HUQUQIY_VERSIYA
    if yosh_tasdiqlandi and user.yosh_tasdigi_at is None:
        user.yosh_tasdigi_at = timezone.now()

    user.save(update_fields=["rozilik_at", "rozilik_versiyasi", "yosh_tasdigi_at"])
    log.info("Rozilik yozildi: user=%s versiya=%s", user.pk, user.rozilik_versiyasi)
