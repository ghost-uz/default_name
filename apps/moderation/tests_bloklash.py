"""Bloklash va uch ogohlantirish (D2-T11)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserBlock
from apps.accounts.services import bloklangan_idlar, bloklash, blokni_yechish
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint
from apps.moderation.models import (
    AuditAction,
    AuditLog,
    ModerationActionType,
    Report,
    ReportReason,
)
from apps.moderation.services import (
    cheklovni_yechish,
    foydalanuvchini_cheklash,
    qaror_qabul_qilish,
    qoidabuzarliklar_soni,
)
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db


def chora(*, staff, user, turi=ModerationActionType.OGOHLANTIRISH):
    """Foydalanuvchiga nisbatan bitta chora ko'radi."""
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)
    return qaror_qabul_qilish(moderator=staff, target=muammo, action=turi)


# ===========================================================================
# ⭐ QABUL MEZONI: bloklangan yoza olmaydi, lekin o'qiy oladi
# ===========================================================================
def test_QABUL_MEZONI_bloklangan_YOZA_OLMAYDI_lekin_OQIY_OLADI(staff, user):
    """⭐ Qabul mezoni.

    ⚠️ `is_active` TEGILMAYDI — u kirishni butunlay yopadi (D0-T2
       dagi farq). Cheklangan odam saytni o'qiy olishi ATAYLAB: u
       o'ziga kelgan javoblarni ko'rishi va nima uchun cheklanganini
       tushunishi kerak.
    """
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    user.refresh_from_db()
    assert user.can_write is False
    assert user.is_active is True

    c = Client()
    c.force_login(user)
    assert c.get("/").status_code == 200


def test_cheklangan_POST_YOZA_OLMAYDI(staff, auth_client, user):
    from apps.common.spam import HONEYPOT_MAYDONI, VAQT_MAYDONI, vaqt_belgisi
    from apps.complaints.factories import CategoryFactory
    from apps.complaints.models import Generation

    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    javob = auth_client.post(
        "/yozish/",
        {
            "title": "Ipoteka olmoqchiman, lekin bank rad etdi",
            "description": "Ikki bankka murojaat qildim va ikkalasi ham rad etdi. Nima qilay?",
            "category": CategoryFactory().pk,
            "generation_tag": Generation.MILLENNIAL,
            VAQT_MAYDONI: vaqt_belgisi(),
            HONEYPOT_MAYDONI: "",
        },
    )

    assert javob.status_code == 403
    assert Complaint.objects.count() == 0


# ===========================================================================
# Cheklash xizmati
# ===========================================================================
def test_vaqtinchalik_cheklov_MUDDATLI(staff, user):
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    user.refresh_from_db()
    assert user.banned_until is not None
    assert user.is_currently_banned is True


def test_MUDDAT_otganda_cheklov_ozi_tugaydi(staff, user):
    """Bayroq hali `True`, lekin muddat o'tgan — cheklov yo'q."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam", kun=1)
    user.refresh_from_db()
    user.banned_until = timezone.now() - timedelta(minutes=1)
    user.save(update_fields=["banned_until"])

    assert user.is_currently_banned is False
    assert user.can_write is True


def test_DOIMIY_blok_muddatsiz(staff, user):
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Takroriy", doimiy=True)

    user.refresh_from_db()
    assert user.banned_until is None
    assert user.is_currently_banned is True


def test_ODDIY_foydalanuvchi_chekla_olmaydi(user, other_user):
    with pytest.raises(PermissionDenied):
        foydalanuvchini_cheklash(moderator=user, user=other_user, sabab="x")


def test_cheklov_YECHILADI(staff, user):
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    cheklovni_yechish(moderator=staff, user=user, sabab="Xato edi")

    user.refresh_from_db()
    assert user.is_banned is False
    assert user.ban_reason == ""
    assert user.can_write is True


def test_cheklash_va_yechish_JURNALGA_tushadi(staff, user):
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")
    cheklovni_yechish(moderator=staff, user=user, sabab="Xato edi")

    cheklov = AuditLog.objects.get(action=AuditAction.FOYDALANUVCHI_CHEKLANDI)
    yechish = AuditLog.objects.get(action=AuditAction.CHEKLOV_YECHILDI)
    assert cheklov.kim == staff.username
    assert cheklov.izoh == "Spam"
    assert yechish.izoh == "Xato edi"


# ===========================================================================
# ⭐ Uch ogohlantirish — avtomatik eskalatsiya
# ===========================================================================
def test_qoidabuzarliklar_SANALADI(staff, user):
    chora(staff=staff, user=user, turi=ModerationActionType.OGOHLANTIRISH)
    chora(staff=staff, user=user, turi=ModerationActionType.YASHIRISH)

    assert qoidabuzarliklar_soni(user=user) == 2


def test_RAD_ETISH_qoidabuzarlik_SANALMAYDI(staff, user):
    """⚠️ `RAD_ETISH` — "qoidabuzarlik yo'q" degani. Uni sanash
    moderator "hammasi joyida" degan qarorini jazoga aylantirardi."""
    chora(staff=staff, user=user, turi=ModerationActionType.RAD_ETISH)

    assert qoidabuzarliklar_soni(user=user) == 0


def test_BEKOR_QILINGAN_chora_sanalmaydi(staff, user):
    """⭐ Moderatorning xatosi foydalanuvchining "jinoyat tarixiga"
    aylanmasin."""
    from apps.moderation.services import qarorni_bekor_qilish

    yozuv = chora(staff=staff, user=user)
    assert qoidabuzarliklar_soni(user=user) == 1

    qarorni_bekor_qilish(moderator=staff, chora=yozuv)

    assert qoidabuzarliklar_soni(user=user) == 0


@override_settings(CHEKLOV_CHEGARASI=3, DOIMIY_BLOK_CHEGARASI=5)
def test_UCHINCHI_chora_VAQTINCHALIK_cheklov_beradi(staff, user):
    """⭐ Task tavsifi: "ogohlantirish -> vaqtinchalik cheklov ->
    doimiy bloklash"."""
    for _ in range(2):
        chora(staff=staff, user=user)
    user.refresh_from_db()
    assert user.is_banned is False

    chora(staff=staff, user=user)

    user.refresh_from_db()
    assert user.is_banned is True
    assert user.banned_until is not None, "uchinchisi VAQTINCHALIK bo'lsin"


@override_settings(CHEKLOV_CHEGARASI=3, DOIMIY_BLOK_CHEGARASI=5)
def test_BESHINCHI_chora_DOIMIY_blok_beradi(staff, user):
    for _ in range(5):
        chora(staff=staff, user=user)

    user.refresh_from_db()
    assert user.is_banned is True
    assert user.banned_until is None


@override_settings(CHEKLOV_CHEGARASI=3, DOIMIY_BLOK_CHEGARASI=5)
def test_DOIMIY_blok_vaqtinchalikka_TUSHIRILMAYDI(staff, user):
    """⚠️ Doimiy blokdan vaqtinchalikka "tushirish" jim yumshatish
    bo'lardi — moderator buni ko'rmasdi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Doimiy", doimiy=True)

    chora(staff=staff, user=user)

    user.refresh_from_db()
    assert user.banned_until is None


@override_settings(CHEKLOV_CHEGARASI=3)
def test_eskalatsiya_JURNALGA_tushadi(staff, user):
    for _ in range(3):
        chora(staff=staff, user=user)

    yozuv = AuditLog.objects.filter(action=AuditAction.FOYDALANUVCHI_CHEKLANDI).first()
    assert yozuv is not None
    assert "Avtomatik" in yozuv.izoh


def test_MUALLIFSIZ_kontentda_eskalatsiya_yiqilmaydi(staff):
    """Muallifi o'chirilgan post ustidan chora ko'rilsa xato bo'lmasin.

    ⚠️ Bu testning birinchi versiyasida `assert ... or True` turgan edi
       — ya'ni HAR DOIM o'tadigan, hech narsani tekshirmaydigan yozuv.
       U "xato bo'lmasa yetarli" degan niyat bilan yozilgan, lekin
       niyatni test EMAS, faqat izoh ifodalardi: chora yozilmay
       qolsa ham test yashil bo'laverardi.
    """
    muammo = ComplaintFactory(author=None)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    yozuv = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    # Chora YOZILDI (eskalatsiya uni to'xtatib qo'ymadi)...
    assert yozuv.pk is not None
    assert yozuv.target_author_id is None
    # ...lekin hech kim cheklanmadi: cheklanadigan odam yo'q.
    assert not AuditLog.objects.filter(
        action=AuditAction.FOYDALANUVCHI_CHEKLANDI
    ).exists()


def test_chegaralar_SOZLAMADA():
    """Chegarani o'zgartirish uchun kod tegilmasin (D2-T4 bilan bir xil
    qoida)."""
    assert settings.CHEKLOV_CHEGARASI < settings.DOIMIY_BLOK_CHEGARASI
    assert settings.CHEKLOV_MUDDATI_KUN > 0


# ===========================================================================
# Foydalanuvchilar o'zaro bloklashi
# ===========================================================================
def test_blok_LENTADAN_chiqaradi(auth_client, user, user_factory):
    yomon = user_factory()
    ComplaintFactory(author=yomon, title="Ko'rinmasin", is_anonymous=False)
    ComplaintFactory(title="Ko'rinsin", is_anonymous=False)

    bloklash(user=user, kim=yomon)
    matn = auth_client.get("/").content.decode()

    assert "Ko&#x27;rinsin" in matn
    assert "Ko&#x27;rinmasin" not in matn


def test_blok_BIR_TOMONLAMA(user, other_user):
    """⚠️ Ikki tomonlama qilish "meni bloklashdi" degan signalni beradi
    va tortishuvni kuchaytiradi — bloklashdan maqsad esa aksincha."""
    bloklash(user=user, kim=other_user)

    assert bloklangan_idlar(user=user) == [other_user.pk]
    assert bloklangan_idlar(user=other_user) == []


def test_bloklangan_CHEKLOV_OLMAYDI(user, other_user):
    """Blok — foydalanuvchining qarori, platformaning emas."""
    bloklash(user=user, kim=other_user)

    other_user.refresh_from_db()
    assert other_user.is_banned is False
    assert other_user.can_write is True


def test_OZINI_bloklab_bolmaydi(user):
    with pytest.raises(ValidationError, match="O'zingizni"):
        bloklash(user=user, kim=user)


def test_TAKRORIY_blok_xato_bermaydi(user, other_user):
    bloklash(user=user, kim=other_user)
    bloklash(user=user, kim=other_user)

    assert UserBlock.objects.count() == 1


def test_blok_YECHILADI(user, other_user):
    bloklash(user=user, kim=other_user)

    blokni_yechish(user=user, kim=other_user)

    assert bloklangan_idlar(user=user) == []


def test_MEHMONDA_blok_royxati_BOSH(anonymous_client):
    from django.contrib.auth.models import AnonymousUser

    assert bloklangan_idlar(user=AnonymousUser()) == []
    assert anonymous_client.get("/").status_code == 200


def test_blok_KORINISH_orqali(auth_client, user, user_factory):
    yomon = user_factory(username="yomonodam")

    javob = auth_client.post(
        reverse("foydalanuvchini_bloklash", args=[yomon.username]),
        {"next": "/"},
        follow=True,
    )

    assert javob.status_code == 200
    assert bloklangan_idlar(user=user) == [yomon.pk]


def test_blokni_yechish_KORINISH_orqali(auth_client, user, user_factory):
    yomon = user_factory()
    bloklash(user=user, kim=yomon)

    auth_client.post(
        reverse("blokni_bekor_qilish", args=[yomon.username]), {"next": "/"}
    )

    assert bloklangan_idlar(user=user) == []


def test_hisob_sahifasida_BLOKNI_YECHISH_yoli_bor(auth_client, user, user_factory):
    """⚠️ Bloklash oson, qaytarish esa topib bo'lmaydigan bo'lsa —
    bu tuzoq."""
    yomon = user_factory(username="yomonodam", first_name="")
    bloklash(user=user, kim=yomon)

    matn = auth_client.get(reverse("hisob")).content.decode()

    assert "Bloklangan foydalanuvchilar" in matn
    assert reverse("blokni_bekor_qilish", args=[yomon.username]) in matn


def test_blok_tugmasi_YECHIM_kartasida(auth_client, user_factory):
    yomon = user_factory()
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, author=yomon, is_anonymous=False)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert reverse("foydalanuvchini_bloklash", args=[yomon.username]) in matn


def test_ANONIM_kontentda_blok_tugmasi_YOQ(auth_client, user_factory):
    """⚠️ Anonim muallifni bloklash uni FOSH QILARDI: tugma qaysi
    hisobga tegishli ekanini ko'rsatib qo'yardi.

    ⚠️ MUAMMO HAM, YECHIM HAM anonim — ataylab. Bu testning birinchi
       versiyasida faqat yechim anonim edi va u dard kartasiga blok
       tugmasi qo'shilganda YIQILDI: sahifada anonim BO'LMAGAN dard
       muallifining tugmasi bor edi. Tekshiruvni toraytirish o'rniga
       (masalan, faqat bitta username'ni qidirish) ikkala kontentni
       ham anonim qildik — shunda `"/bloklash/@" not in matn` degan
       keng tekshiruv kuchida qoladi va KELAJAKDA qo'shiladigan
       tugmalarni ham qoplaydi.
    """
    muammo = ComplaintFactory(is_anonymous=True)
    SolutionFactory(complaint=muammo, author=user_factory(), is_anonymous=True)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert "/bloklash/@" not in matn


def test_blok_tugmasi_DARD_sahifasida(auth_client, user_factory):
    """Dard muallifini ham bloklay olish kerak — blok lentadan
    chiqaradi, lekin odam bloklamoqchi bo'lgan joyda tugma bo'lmasa,
    u yo'lni topa olmaydi."""
    yomon = user_factory(username="yomonmuallif")
    muammo = ComplaintFactory(author=yomon, is_anonymous=False)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert reverse("foydalanuvchini_bloklash", args=[yomon.username]) in matn


def test_BLOKLANGAN_dard_muallifida_tugma_YECHISHGA_aylanadi(
    auth_client, user, user_factory
):
    """⚠️ Allaqachon bloklangan odamni yana bloklashni taklif qilish
    interfeysning yolg'oni bo'lardi."""
    yomon = user_factory(username="yomonmuallif")
    muammo = ComplaintFactory(author=yomon, is_anonymous=False)
    bloklash(user=user, kim=yomon)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert reverse("blokni_bekor_qilish", args=[yomon.username]) in matn
    assert reverse("foydalanuvchini_bloklash", args=[yomon.username]) not in matn


# ===========================================================================
# ⭐ Cheklov banneri — "nima uchun cheklanganini tushunishi kerak"
# ===========================================================================
def test_BANNER_cheklanganga_HAR_SAHIFADA_korinadi(staff, auth_client, user):
    """⭐ `foydalanuvchini_cheklash()` mantiqi shunga qurilgan: odam
    o'qiy oladi, CHUNKI u sababni bilishi kerak. Xabar faqat yozish
    sahifasida tursa, bu va'da bajarilmasdi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Takroriy spam")

    for yol in ("/", reverse("hisob")):
        matn = auth_client.get(yol).content.decode()
        assert "cheklangan" in matn, f"{yol} da banner yo'q"
        assert "Takroriy spam" in matn, f"{yol} da SABAB yo'q"


def test_BANNER_muddatni_MAHALLIY_vaqtda_korsatadi(staff, auth_client, user):
    """⚠️ `USE_TZ = True` — baza UTC'da saqlaydi, shablon esa
    `TIME_ZONE` ("Asia/Tashkent") da chizadi: farq 5 soat.

    Bu testning birinchi versiyasi `banned_until` ni to'g'ridan-to'g'ri
    solishtirgan edi va YIQILDI — kod emas, test noto'g'ri edi.
    Toshkentdagi odam cheklov "23:19 gacha" ekanini ko'rishi kerak,
    "18:19 UTC" emas; bu test aynan shuni qotiradi, chunki xato
    (`|date` o'rniga xom qiymat) hech qanday belgi bermasdi —
    shunchaki 5 soat noto'g'ri vaqt ko'rsatilardi.
    """
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam", kun=7)
    user.refresh_from_db()

    matn = auth_client.get("/").content.decode()

    mahalliy = timezone.localtime(user.banned_until)
    assert mahalliy.strftime("%H:%M") in matn
    assert user.banned_until.strftime("%H:%M") not in matn, (
        "UTC vaqt chiqyapti — shablonda `|date` filtri tushib qolganmi?"
    )


def test_BANNER_DOIMIY_blokda_boshqacha(staff, auth_client, user):
    """⚠️ Vaqtinchalik cheklov "kuting" degani, doimiysi "bu tugadi".
    Bir xil ko'rinsa, odam muddat tugashini kutib o'tirardi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Tahdid", doimiy=True)

    matn = auth_client.get("/").content.decode()

    assert "doimiy bloklangan" in matn.lower()
    # Doimiy blokda "kuting" emas, "bog'laning" yo'li ko'rsatiladi.
    assert reverse("boglanish") in matn


def test_BANNER_MUDDAT_otgach_YOQOLADI(staff, auth_client, user):
    """⚠️ `is_banned` bayrog'i muddat o'tgach ham `True` turadi (uni
    tozalaydigan fon vazifasi yo'q). Banner bayroqqa qarasa, odam
    cheklov tugagandan keyin ham xabarni ko'raverardi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")
    user.refresh_from_db()
    user.banned_until = timezone.now() - timedelta(minutes=1)
    user.save(update_fields=["banned_until"])

    matn = auth_client.get("/").content.decode()

    assert "Hisobingiz" not in matn


def test_BANNER_ODDIY_foydalanuvchida_YOQ(auth_client):
    assert "Hisobingiz" not in auth_client.get("/").content.decode()


def test_BANNER_MEHMONDA_yiqilmaydi(anonymous_client):
    """`AnonymousUser` da `is_currently_banned` yo'q — shablon buni
    jim yutishi va sahifa ochilishi kerak."""
    assert anonymous_client.get("/").status_code == 200


def test_BANNER_qoshimcha_SOROV_qilmaydi(staff, auth_client, user):
    """⚠️ Banner `request.user` dagi maydonlarni o'qiydi — u sessiya
    bilan allaqachon yuklangan. Kontekst protsessori qo'shilsa lenta
    so'rov-sanog'i o'zgarardi (`test_QATIY_sonlar`)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    auth_client.get("/")  # sessiyani ilitamiz
    with CaptureQueriesContext(connection) as toza:
        auth_client.get("/")

    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")
    with CaptureQueriesContext(connection) as cheklangan:
        auth_client.get("/")

    assert len(cheklangan) == len(toza)


# ===========================================================================
# ⭐ Bloklangan foydalanuvchi javobi — yig'ilgan, lekin o'chirilmagan
# ===========================================================================
def test_BLOKLANGAN_javob_YIGILADI_lekin_YOQOLMAYDI(auth_client, user, user_factory):
    """⭐ Foydalanuvchi qarori: javob olib tashlansa "3 yechim" deb
    yozilgan joyda 2 tasi ko'rinardi va javoblar zanjiri uzilardi."""
    yomon = user_factory()
    muammo = ComplaintFactory()
    SolutionFactory(
        complaint=muammo, author=yomon, is_anonymous=False, content="Yomon javob matni"
    )
    bloklash(user=user, kim=yomon)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-bloklangan" in matn, "yig'iladigan blok yo'q"
    assert "Bloklangan foydalanuvchi javobi" in matn
    # ⚠️ Kontent SAHIFADA qoladi — `<details>` uni yashiradi, o'chirmaydi.
    #    Shu sababli yechimlar SANOG'I ham o'zgarmaydi.
    assert "Yomon javob matni" in matn


def test_BLOKLANMAGAN_javob_YIGILMAYDI(auth_client, user_factory):
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, author=user_factory(), is_anonymous=False)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-bloklangan" not in matn


def test_ANONIM_javob_BLOKLANGAN_muallifda_HAM_yigilmaydi(
    auth_client, user, user_factory
):
    """⚠️⚠️ ANONIMLIK BLOKDAN USTUN.

    "Bloklangan foydalanuvchi javobi" yozuvi anonim postda o'quvchiga
    muallif KIM ekanini aytib qo'yardi — u o'z bloklaganlari ro'yxatini
    biladi. Ya'ni blok anonimlikni ochadigan asbobga aylanardi.

    Lentada bunday xavf yo'q: u yerda post shunchaki YO'Q bo'ladi va
    yo'qlik signal bermaydi.
    """
    yomon = user_factory()
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, author=yomon, is_anonymous=True)
    bloklash(user=user, kim=yomon)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-bloklangan" not in matn


# ===========================================================================
# ⭐ Moderator navbati — tarix va qo'lda cheklash
# ===========================================================================
def test_NAVBATDA_qoidabuzarliklar_soni_korinadi(staff_client, staff, user):
    chora(staff=staff, user=user)
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert "avval 1 ta chora" in matn


def test_navbat_sanogi_BEKOR_QILINGANNI_hisoblamaydi(staff_client, staff, user):
    """⚠️ Navbatdagi raqam va avtomatika BIR XIL mantiqqa tayanishi
    shart — aks holda ekranda "2" turgan paytda avtomatika boshqa son
    bo'yicha qaror qabul qilardi."""
    from apps.moderation.services import qarorni_bekor_qilish

    yozuv = chora(staff=staff, user=user)
    qarorni_bekor_qilish(moderator=staff, chora=yozuv)
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert "avval" not in matn


def test_navbat_sanogi_BITTA_SOROVDA_olinadi(staff_client, staff, user_factory):
    """⚠️ Sanoq `Holat` xossasi bo'lsa, 10 holatli navbat 10 ta
    qo'shimcha so'rov qilardi — D2-T2 hal qilgan muammoning
    so'rovlardagi ko'rinishi.

    ⚠️ Bu test `.order_by()` ni ham qo'riqlaydi: `Meta.ordering`
       GROUP BY ga tushsa sonlar hammasi 1 bo'lardi va sanoq
       so'rovi baribir bitta bo'lardi — shuning uchun quyida
       SONNING O'ZI ham tekshiriladi.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def navbatni_toldirish(nechta: int) -> None:
        for _ in range(nechta):
            muallif = user_factory()
            chora(staff=staff, user=muallif)
            muammo = ComplaintFactory(author=muallif)
            Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    yol = reverse("moderatsiya_navbat")
    navbatni_toldirish(2)
    staff_client.get(yol)  # sessiyani ilitamiz
    with CaptureQueriesContext(connection) as kam:
        staff_client.get(yol)

    navbatni_toldirish(6)
    with CaptureQueriesContext(connection) as kop:
        staff_client.get(yol)

    assert len(kam) == len(kop), (
        f"So'rov soni navbat uzunligiga bog'liq: {len(kam)} -> {len(kop)}"
    )


def test_navbat_sanogi_META_ORDERING_dan_BUZILMAYDI(staff, user):
    """⚠️⚠️ `ModerationAction.Meta.ordering = ("-created_at",)`.

    `values(...).annotate(...)` da Django standart tartibni GROUP BY
    ga QO'SHIB YUBORADI — guruhlash `(muallif, created_at)` bo'yicha
    ketardi va HAR CHORA o'ziga alohida guruh bo'lardi. Natijada
    hamma sanoq `1` chiqardi va HECH QANDAY XATO BO'LMASDI.

    Shuning uchun bu yerda aynan RAQAM tekshiriladi.
    """
    from apps.moderation.selectors import _qoidabuzarlik_sonlari

    for _ in range(3):
        chora(staff=staff, user=user)

    assert _qoidabuzarlik_sonlari({user.pk}) == {user.pk: 3}


@override_settings(CHEKLOV_CHEGARASI=3, DOIMIY_BLOK_CHEGARASI=5)
def test_navbat_KEYINGI_chora_oqibatini_OLDINDAN_aytadi(staff_client, staff, user):
    """⭐ Ogohlantirish tugmasini bosgan moderator odamni bloklab
    qo'yganini KEYIN bilib olishi noto'g'ri."""
    for _ in range(2):
        chora(staff=staff, user=user)
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert "AVTOMATIK" in matn


def test_navbat_BIRINCHI_chorada_ogohlantirmaydi(staff_client, user):
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert "AVTOMATIK" not in matn


def test_MODERATOR_qolda_cheklaydi(staff_client, user):
    """⚠️ Uch ogohlantirish — o'rtacha holat uchun. Og'ir holatda
    moderator uchtasini kutib o'tirmasligi kerak."""
    javob = staff_client.post(
        reverse("moderatsiya_cheklash", args=[user.pk]),
        {"sabab": "Uyushtirilgan hujum", "doimiy": "0"},
    )

    assert javob.status_code == 302
    user.refresh_from_db()
    assert user.is_currently_banned is True
    assert user.banned_until is not None
    assert user.ban_reason == "Uyushtirilgan hujum"


def test_MODERATOR_qolda_DOIMIY_bloklaydi(staff_client, user):
    staff_client.post(
        reverse("moderatsiya_cheklash", args=[user.pk]),
        {"sabab": "Tahdid", "doimiy": "1"},
    )

    user.refresh_from_db()
    assert user.is_currently_banned is True
    assert user.banned_until is None


def test_qolda_cheklov_JURNALGA_tushadi(staff_client, staff, user):
    """⚠️ Django admin ham `is_banned` ni o'zgartira oladi, lekin u
    jurnalga HECH NARSA yozmaydi — shuning uchun bu yo'l bor."""
    staff_client.post(
        reverse("moderatsiya_cheklash", args=[user.pk]),
        {"sabab": "Uyushtirilgan hujum", "doimiy": "0"},
    )

    yozuv = AuditLog.objects.get(action=AuditAction.FOYDALANUVCHI_CHEKLANDI)
    assert yozuv.kim == staff.username
    assert yozuv.izoh == "Uyushtirilgan hujum"


def test_MODERATOR_OZINI_chekla_olmaydi(staff_client, staff):
    """Xato bosish, qasd emas — lekin oqibati bir xil: moderator o'z
    hisobini yopib qo'yardi."""
    staff_client.post(reverse("moderatsiya_cheklash", args=[staff.pk]), {"sabab": "x"})

    staff.refresh_from_db()
    assert staff.is_banned is False


def test_ODDIY_foydalanuvchiga_cheklash_manzili_KORINMAYDI(auth_client, other_user):
    """⚠️ Staff bo'lmaganga 404 — 403 emas: 403 manzil borligini
    tasdiqlab berardi (`moderator_kerak`)."""
    javob = auth_client.post(
        reverse("moderatsiya_cheklash", args=[other_user.pk]), {"sabab": "x"}
    )

    assert javob.status_code == 404
    other_user.refresh_from_db()
    assert other_user.is_banned is False


def test_MODERATOR_cheklovni_yechadi(staff_client, staff, user):
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    staff_client.post(
        reverse("moderatsiya_cheklov_yechish", args=[user.pk]),
        {"sabab": "Apellyatsiya qanoatlantirildi"},
    )

    user.refresh_from_db()
    assert user.is_banned is False
    assert AuditLog.objects.filter(action=AuditAction.CHEKLOV_YECHILDI).exists()


def test_navbatda_CHEKLANGAN_muallifda_YECHISH_yoli_bor(staff_client, staff, user):
    """⚠️ Cheklash bir bosish, yechish esa faqat adminda bo'lsa —
    moderator xatosini tuzatmaydi, chunki yo'l ko'rinmaydi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")
    muammo = ComplaintFactory(author=user)
    Report.objects.create(complaint=muammo, reason=ReportReason.SPAM)

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert reverse("moderatsiya_cheklov_yechish", args=[user.pk]) in matn
    assert reverse("moderatsiya_cheklash", args=[user.pk]) not in matn


# ===========================================================================
# ⭐ Cheklov muddati — jim yumshatishga qarshi
# ===========================================================================
def test_muddat_CHEKLOV_YOQ_bolsa_soralganini_beradi(user):
    from apps.moderation.services import yangi_muddat

    natija = yangi_muddat(user=user, kun=7)

    assert natija > timezone.now() + timedelta(days=6)
    assert natija < timezone.now() + timedelta(days=8)


def test_MUDDATI_TUGAGAN_cheklov_yangisini_QISQARTIRMAYDI(user):
    """⚠️ `is_banned` bayrog'i muddat o'tgach ham `True` turadi va
    `banned_until` eski sanada qoladi. `max` uni o'z-o'zidan chetlab
    o'tadi (u `hozir` dan kichik) — bu tasodif emas, shu yerda
    qotirilgan.
    """
    from apps.moderation.services import yangi_muddat

    user.banned_until = timezone.now() - timedelta(days=100)

    natija = yangi_muddat(user=user, kun=7)

    assert natija > timezone.now()


def test_UZUNROQ_cheklov_QISQARMAYDI(user):
    """⭐ Bu funksiya mavjudligining asosiy sababi.

    Moderator odamni 30 kunga chekladi; ikki kundan keyin unga
    standart 7 kunlik cheklov tushdi. Sodda `now + kun` yozuvi
    muddatni 21 kunga QISQARTIRARDI — ya'ni yangi jazo jazoni
    yengillashtirardi.
    """
    from apps.moderation.services import yangi_muddat

    uzoq = timezone.now() + timedelta(days=30)
    user.banned_until = uzoq

    natija = yangi_muddat(user=user, kun=7)

    assert natija == uzoq


def test_QISQAROQ_cheklov_UZAYADI(user):
    from apps.moderation.services import yangi_muddat

    user.banned_until = timezone.now() + timedelta(days=2)

    natija = yangi_muddat(user=user, kun=7)

    assert natija > timezone.now() + timedelta(days=6)


def test_muddatlar_QOSHILMAYDI(user):
    """⚠️ Ikkinchi yo'l — qolgan vaqt USTIGA qo'shish — ataylab
    RAD ETILGAN: muddatlar tez o'sib (30 + 7 + 7 + 7) amalda doimiy
    blokka aylanardi, lekin "doimiy" deb ATALMAGAN holda. Yashirin
    doimiy blok esa apellyatsiyani ham, tushuntirishni ham imkonsiz
    qiladi.
    """
    from apps.moderation.services import yangi_muddat

    user.banned_until = timezone.now() + timedelta(days=30)

    natija = yangi_muddat(user=user, kun=7)

    assert natija < timezone.now() + timedelta(days=31), "muddatlar qo'shilib ketdi"


def test_TAKRORIY_cheklov_muddatni_QISQARTIRMAYDI(staff, user):
    """⭐ Yuqoridagi qoidaning to'liq oqim orqali tekshiruvi."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Og'ir holat", kun=30)
    user.refresh_from_db()
    uzoq = user.banned_until

    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Yana spam", kun=7)

    user.refresh_from_db()
    assert user.banned_until == uzoq
    # ...lekin YANGI SABAB yoziladi: oxirgi qaror nimaga tegishli
    # ekani ko'rinib turishi kerak.
    assert user.ban_reason == "Yana spam"


@override_settings(CHEKLOV_CHEGARASI=3, DOIMIY_BLOK_CHEGARASI=99)
def test_AVTOMATIK_eskalatsiya_ham_QISQARTIRMAYDI(staff, user):
    """⚠️ Avtomatika ham shu yo'ldan o'tadi: moderatorning uzoq
    cheklovini avtomatik 7 kunlik chora yuvib yubormasligi kerak."""
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Og'ir holat", kun=30)
    user.refresh_from_db()
    uzoq = user.banned_until

    for _ in range(3):
        chora(staff=staff, user=user)

    user.refresh_from_db()
    assert user.banned_until == uzoq


def test_YIGILGAN_javob_ichida_tugma_YECHISHGA_aylanadi(
    auth_client, user, user_factory
):
    """⚠️ Yig'ilgan blokni ochgan odam ichkarida yana "Bloklash" ni
    ko'rsa, interfeys o'zi bilan ziddiyatga tushardi."""
    yomon = user_factory(username="yomonjavob")
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, author=yomon, is_anonymous=False)
    bloklash(user=user, kim=yomon)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert reverse("blokni_bekor_qilish", args=[yomon.username]) in matn
    assert reverse("foydalanuvchini_bloklash", args=[yomon.username]) not in matn
