"""Kontakt so'rovi va yopiq suhbat (D6-T5)."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import TelegramUserFactory
from apps.accounts.models import UserBlock
from apps.common.models import ModerationStatus
from apps.complaints.factories import AnonimComplaintFactory, ComplaintFactory
from apps.moderation.models import Report, ReportReason, ReportStatus
from apps.moderation.selectors import navbat
from apps.notifications.models import BildirishnomaTuri, Notification
from apps.solutions.factories import SolutionFactory
from apps.solutions.services import accept_solution
from apps.suhbat.models import KontaktSorovi, SorovHolati, Suhbat, Xabar
from apps.suhbat.services import (
    kontakt_sorash,
    sorovga_javob,
    suhbatni_yopish,
    xabar_yozish,
)

pytestmark = pytest.mark.django_db


def _qabul_qilingan(*, anonim_muammo: bool = False, anonim_yechim: bool = False):
    """Qabul qilingan yechim + ikki tomon."""
    fabrika = AnonimComplaintFactory if anonim_muammo else ComplaintFactory
    muammo = fabrika()
    yechim = SolutionFactory(complaint=muammo, is_anonymous=anonim_yechim)
    accept_solution(solution=yechim, by_user=muammo.author)
    yechim.refresh_from_db()
    return muammo, yechim


def _suhbat_ochish(*, anonim_muammo=False, anonim_yechim=False):
    muammo, yechim = _qabul_qilingan(
        anonim_muammo=anonim_muammo, anonim_yechim=anonim_yechim
    )
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)
    sorovga_javob(sorov=sorov, user=yechim.author, qabul=True)
    sorov.refresh_from_db()
    return muammo, yechim, sorov.suhbat


# ===========================================================================
# 1. ⚠️⚠️ Qabul mezoni: rozilikSIZ hech narsa ochilmaydi
# ===========================================================================
def test_SOROV_OZI_suhbat_OCHMAYDI():
    """⚠️⚠️ D6-T5 QABUL MEZONI 1.

    So'rov yuborilishi bilan kanal ochilib qolsa, «rozilik» degan
    tushuncha umuman bo'lmasdi.
    """
    muammo, yechim = _qabul_qilingan()

    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    assert sorov.holat == SorovHolati.KUTILMOQDA
    assert Suhbat.objects.count() == 0


def test_ANONIM_muallifning_ISMI_HECH_QAYERDA_yoq():
    """⚠️⚠️ QABUL MEZONI 1: anonim muallifning kontakti ochilmaydi.

    Bu yerda ATAYLAB kontakt EMAS, ISM tekshiriladi: kontakt umuman
    ochilmaydi (Telegram nomi hech qachon berilmaydi), ya'ni yagona
    haqiqiy xavf — ismning suhbatda ko'rinishi.
    """
    muammo, _, suhbat = _suhbat_ochish(anonim_muammo=True)

    nom = suhbat.korinadigan_nom(muammo.author)

    assert muammo.author.display_name not in nom
    assert nom == "Anonim (muammo muallifi)"


def test_ANONIM_YECHIM_muallifi_ham_yashiringan():
    muammo, yechim = _qabul_qilingan(anonim_yechim=True)
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)
    sorovga_javob(sorov=sorov, user=yechim.author, qabul=True)
    suhbat = Suhbat.objects.get()

    nom = suhbat.korinadigan_nom(yechim.author)

    assert yechim.author.display_name not in nom
    assert nom == "Anonim (yechim muallifi)"


def test_OCHIQ_muallif_ISMI_bilan_korinadi():
    muammo, _, suhbat = _suhbat_ochish()

    assert suhbat.korinadigan_nom(muammo.author) == muammo.author.display_name


def test_XABAR_NOMI_ANONIMLIKNI_hurmat_qiladi():
    """⚠️ Shablon `xabar.korinadigan_nom` ni ishlatadi — u
    `author.display_name` ga cho'zilmasligi kerak."""
    muammo, _, suhbat = _suhbat_ochish(anonim_muammo=True)

    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert muammo.author.display_name not in xabar.korinadigan_nom


def test_SUHBAT_SAHIFASIDA_anonim_ismi_YOQ(client):
    muammo, yechim, suhbat = _suhbat_ochish(anonim_muammo=True)
    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    client.force_login(yechim.author)
    sahifa = client.get(suhbat.get_absolute_url()).content.decode()

    assert muammo.author.display_name not in sahifa
    assert muammo.author.username not in sahifa


# ===========================================================================
# 2. ⚠️ Qabul mezoni: rad etish imkoniyati
# ===========================================================================
def test_RAD_ETISH_suhbat_OCHMAYDI():
    """⚠️ D6-T5 QABUL MEZONI 2."""
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    sorovga_javob(sorov=sorov, user=yechim.author, qabul=False)

    sorov.refresh_from_db()
    assert sorov.holat == SorovHolati.RAD_ETILDI
    assert Suhbat.objects.count() == 0


def test_RAD_ETILGANDAN_KEYIN_qayta_sorab_bolmaydi():
    """⚠️ Aks holda «yo'q» javobi hech narsani anglatmasdi va rad
    etish tugmasi bezovtalikni to'xtatmasdi."""
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)
    sorovga_javob(sorov=sorov, user=yechim.author, qabul=False)

    with pytest.raises(ValidationError):
        kontakt_sorash(solution=yechim, soragan=muammo.author)


def test_SORAGAN_ODAM_OZI_qabul_QILA_OLMAYDI():
    """⚠️⚠️ Aks holda rozilik talabi bir bosishda chetlab o'tilardi."""
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    with pytest.raises(PermissionDenied):
        sorovga_javob(sorov=sorov, user=muammo.author, qabul=True)


def test_BEGONA_javob_BERA_OLMAYDI():
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    with pytest.raises(PermissionDenied):
        sorovga_javob(sorov=sorov, user=TelegramUserFactory(), qabul=True)


def test_IKKI_MARTA_javob_berib_bolmaydi():
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)
    sorovga_javob(sorov=sorov, user=yechim.author, qabul=True)

    with pytest.raises(ValidationError):
        sorovga_javob(sorov=sorov, user=yechim.author, qabul=False)


# ===========================================================================
# 3. So'rov shartlari
# ===========================================================================
def test_QABUL_QILINMAGAN_yechimda_sorab_bolmaydi():
    """⚠️ Task: «yechim qabul qilingandan keyin». Bu shart bezovtalikka
    ham qarshi: tasodifiy odam istalgan postga suhbat so'rab yura
    olmaydi."""
    yechim = SolutionFactory()

    with pytest.raises(ValidationError):
        kontakt_sorash(solution=yechim, soragan=yechim.complaint.author)


def test_BEGONA_sorov_YUBORA_OLMAYDI():
    _, yechim = _qabul_qilingan()

    with pytest.raises(PermissionDenied):
        kontakt_sorash(solution=yechim, soragan=TelegramUserFactory())


def test_BLOKLANGAN_odamga_sorov_YUBORILMAYDI():
    """⚠️⚠️ `UserBlock` bir tomonlama (D2-T11), lekin shaxsiy kanal
    OCHISH boshqa gap: bloklagan odamga so'rov kelishi blokning butun
    ma'nosini yo'qotardi."""
    muammo, yechim = _qabul_qilingan()
    UserBlock.objects.create(user=yechim.author, blocked=muammo.author)

    with pytest.raises(ValidationError):
        kontakt_sorash(solution=yechim, soragan=muammo.author)


def test_BLOK_TESKARI_yonalishda_ham_toxtatadi():
    muammo, yechim = _qabul_qilingan()
    UserBlock.objects.create(user=muammo.author, blocked=yechim.author)

    with pytest.raises(ValidationError):
        kontakt_sorash(solution=yechim, soragan=muammo.author)


def test_CHEKLANGAN_odam_sorov_YUBORA_OLMAYDI():
    muammo, yechim = _qabul_qilingan()
    muammo.author.is_banned = True
    muammo.author.save(update_fields=["is_banned"])

    with pytest.raises(PermissionDenied):
        kontakt_sorash(solution=yechim, soragan=muammo.author)


def test_YECHIM_MUALLIFI_ham_sorab_oladi():
    """⚠️ So'rovni HAR IKKI TOMON boshlashi mumkin."""
    muammo, yechim = _qabul_qilingan()

    sorov = kontakt_sorash(solution=yechim, soragan=yechim.author)

    assert sorov.qarshi_tomon_id == muammo.author_id


# ===========================================================================
# 4. Xabar yozish
# ===========================================================================
def test_XABAR_YOZILADI():
    muammo, _, suhbat = _suhbat_ochish()

    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert xabar.content == "Salom"
    assert list(suhbat.xabarlar.all()) == [xabar]


def test_BEGONA_YOZA_OLMAYDI():
    _, _, suhbat = _suhbat_ochish()

    with pytest.raises(PermissionDenied):
        xabar_yozish(suhbat=suhbat, author=TelegramUserFactory(), matn="Salom")


def test_CHEKLANGAN_odam_SUHBATDA_HAM_yoza_olmaydi():
    """⚠️⚠️ Usiz blok «lentada yozolmayman, shaxsiyda yozaveraman»
    degan teshikka aylanardi — va shaxsiy kanal bezovtalik uchun eng
    qulay joy."""
    muammo, _, suhbat = _suhbat_ochish()
    muammo.author.is_banned = True
    muammo.author.save(update_fields=["is_banned"])

    with pytest.raises(PermissionDenied):
        xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")


def test_YOPIQ_suhbatga_YOZIB_BOLMAYDI():
    """⚠️ «Yopish» tugmasi haqiqiy to'xtatish bo'lishi kerak."""
    muammo, yechim, suhbat = _suhbat_ochish()
    suhbatni_yopish(suhbat=suhbat, user=muammo.author)

    with pytest.raises(ValidationError):
        xabar_yozish(suhbat=suhbat, author=yechim.author, matn="Salom")


def test_BOSH_xabar_RAD_etiladi():
    muammo, _, suhbat = _suhbat_ochish()

    with pytest.raises(ValidationError):
        xabar_yozish(suhbat=suhbat, author=muammo.author, matn="   ")


def test_YOPILGAN_suhbat_YOZISHMASI_QOLADI():
    """⚠️ O'chirish shikoyat uchun dalilni yo'q qilardi."""
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    suhbatni_yopish(suhbat=suhbat, user=yechim.author)

    assert suhbat.xabarlar.count() == 1


def test_HAR_IKKI_TOMON_yopa_oladi():
    _, yechim, suhbat = _suhbat_ochish()

    suhbatni_yopish(suhbat=suhbat, user=yechim.author)

    suhbat.refresh_from_db()
    assert suhbat.yopiqmi is True
    assert suhbat.yopgan_id == yechim.author_id


# ===========================================================================
# 5. ⚠️⚠️ Qabul mezoni: chat moderatsiya qamrovida
# ===========================================================================
def test_XABARGA_SHIKOYAT_qilish_mumkin(client):
    """⚠️⚠️ D6-T5 QABUL MEZONI 3."""
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Yomon gap")

    client.force_login(yechim.author)
    javob = client.post(
        reverse("xabar_shikoyat", args=[xabar.pk]),
        {"reason": ReportReason.HAQORAT, "comment": ""},
        follow=True,
    )

    assert javob.status_code == 200
    assert Report.objects.filter(xabar=xabar).count() == 1


def test_SHIKOYAT_QILINGAN_xabar_NAVBATGA_tushadi():
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Yomon gap")
    Report.objects.create(
        reporter=yechim.author, xabar=xabar, reason=ReportReason.HAQORAT
    )

    holatlar = navbat()

    assert len(holatlar) == 1
    assert holatlar[0].turi == "xabar"
    assert holatlar[0].target.pk == xabar.pk


def test_BEGONA_xabarga_SHIKOYAT_QILA_OLMAYDI(client):
    """⚠️⚠️ Shikoyat manzili yozishmani begonaga ochib beradigan
    teshik bo'lmasin — 404, 403 EMAS."""
    muammo, _, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    client.force_login(TelegramUserFactory())
    javob = client.get(reverse("xabar_shikoyat", args=[xabar.pk]))

    assert javob.status_code == 404


def test_YASHIRILGAN_xabar_ISHTIROKCHIGA_HAM_korinmaydi(client):
    """⚠️⚠️ Chora ko'rilgan xabar suhbatda turaversa, moderatsiyaning
    ma'nosi qolmasdi (D2-T3 invariantining suhbatdagi shakli)."""
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Yomon gap")
    xabar.moderation_status = ModerationStatus.HIDDEN
    xabar.save(update_fields=["moderation_status"])

    client.force_login(yechim.author)
    sahifa = client.get(suhbat.get_absolute_url()).content.decode()

    assert "Yomon gap" not in sahifa


def test_INQIROZ_belgisi_SUHBATDA_ham_ishlaydi():
    """⚠️⚠️ Eng og'ir gap aynan shaxsiy yozishmada aytiladi va u
    ommaviy lentada hech qachon ko'rinmaydi — bu tekshiruvsiz signal
    butunlay yo'qolardi (D2-T6)."""
    muammo, _, suhbat = _suhbat_ochish()

    xabar = xabar_yozish(
        suhbat=suhbat, author=muammo.author, matn="o'zimni o'ldirmoqchiman"
    )

    xabar.refresh_from_db()
    assert xabar.inqiroz_aniqlandi is True
    assert Report.objects.filter(
        xabar=xabar, reason=ReportReason.XAVF, reporter__isnull=True
    ).exists()


def test_INQIROZ_belgisi_xabarni_YASHIRMAYDI():
    """⚠️ D2-T6: aniqlash TSENZURA EMAS."""
    muammo, _, suhbat = _suhbat_ochish()

    xabar = xabar_yozish(
        suhbat=suhbat, author=muammo.author, matn="o'zimni o'ldirmoqchiman"
    )

    xabar.refresh_from_db()
    assert xabar.moderation_status == ModerationStatus.VISIBLE
    assert xabar.is_deleted is False


def test_MODERATOR_xabarni_YASHIRA_oladi(client, staff):
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Yomon gap")
    Report.objects.create(
        reporter=yechim.author, xabar=xabar, reason=ReportReason.HAQORAT
    )

    client.force_login(staff)
    javob = client.post(
        reverse("moderatsiya_qaror_xabar", args=[xabar.pk]),
        {"action": "yashirish", "izoh": "Haqorat"},
    )

    assert javob.status_code == 302
    xabar.refresh_from_db()
    assert xabar.moderation_status == ModerationStatus.HIDDEN
    assert Report.objects.get(xabar=xabar).status == ReportStatus.HAL_QILINDI


# ===========================================================================
# 6. Kirish nazorati
# ===========================================================================
def test_BEGONA_suhbatni_KORA_OLMAYDI(client):
    """⚠️⚠️ 404, 403 EMAS: `403` kimning kim bilan yozishayotganini
    tasdiqlab berardi."""
    _, _, suhbat = _suhbat_ochish()

    client.force_login(TelegramUserFactory())
    javob = client.get(suhbat.get_absolute_url())

    assert javob.status_code == 404


def test_MEHMON_KIRISHGA_yonaltiriladi(anonymous_client):
    _, _, suhbat = _suhbat_ochish()

    javob = anonymous_client.get(suhbat.get_absolute_url())

    assert javob.status_code == 302
    assert "/kirish/" in javob["Location"]


def test_SUHBAT_sahifasi_NOINDEX(client):
    muammo, _, suhbat = _suhbat_ochish()

    client.force_login(muammo.author)
    sahifa = client.get(suhbat.get_absolute_url()).content.decode()

    assert 'content="noindex, nofollow"' in sahifa


def test_ROYXATDA_faqat_OZ_suhbatlari(client):
    muammo, _, suhbat = _suhbat_ochish()
    _suhbat_ochish()  # boshqalarning suhbati

    client.force_login(muammo.author)
    javob = client.get(reverse("suhbatlar"))

    assert list(javob.context["suhbatlar"]) == [suhbat]


def test_ROYXATDA_javob_KUTAYOTGAN_sorov_korinadi(client):
    muammo, yechim = _qabul_qilingan()
    kontakt_sorash(solution=yechim, soragan=muammo.author)

    client.force_login(yechim.author)
    javob = client.get(reverse("suhbatlar"))

    assert len(javob.context["sorovlar"]) == 1


def test_OZ_SOROVI_javob_kutayotganlar_royxatida_YOQ(client):
    muammo, yechim = _qabul_qilingan()
    kontakt_sorash(solution=yechim, soragan=muammo.author)

    client.force_login(muammo.author)
    javob = client.get(reverse("suhbatlar"))

    assert list(javob.context["sorovlar"]) == []


# ===========================================================================
# 7. Bildirishnomalar
# ===========================================================================
def test_SOROV_bildirishnoma_yuboradi():
    muammo, yechim = _qabul_qilingan()

    kontakt_sorash(solution=yechim, soragan=muammo.author)

    # ⚠️ `accept_solution` allaqachon YECHIM_QABUL yozuvini yaratgan —
    #    tur bo'yicha filtrlanadi.
    yozuv = Notification.objects.get(
        recipient=yechim.author, turi=BildirishnomaTuri.KONTAKT_SOROVI
    )
    assert yozuv.turi == BildirishnomaTuri.KONTAKT_SOROVI
    # ⚠️ `actor` YO'Q: so'ragan odam anonim yozgan bo'lishi mumkin.
    assert yozuv.actor is None


def test_BILDIRISHNOMA_MATNIDA_ism_YOQ():
    muammo, yechim = _qabul_qilingan(anonim_muammo=True)

    kontakt_sorash(solution=yechim, soragan=muammo.author)

    matn = Notification.objects.get(
        recipient=yechim.author, turi=BildirishnomaTuri.KONTAKT_SOROVI
    ).matn
    assert muammo.author.display_name not in matn


def test_JAVOB_bildirishnomasi_RAD_ETILGANDA_HAM_yuboriladi():
    """⚠️ Javobsiz qolgan so'rov odamni kutishda qoldirardi."""
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)
    Notification.objects.all().delete()

    sorovga_javob(sorov=sorov, user=yechim.author, qabul=False)

    yozuv = Notification.objects.get(recipient=muammo.author)
    assert yozuv.turi == BildirishnomaTuri.KONTAKT_JAVOBI
    assert "rad etildi" in yozuv.matn


def test_YANGI_XABAR_bildirishnomasi_TAKRORLANMAYDI():
    """⚠️⚠️ O'qilmagan bildirishnoma turganda yangisi yaratilmaydi —
    aks holda faol suhbat o'nlab Telegram xabari berardi (D5-T4)."""
    muammo, yechim, suhbat = _suhbat_ochish()
    Notification.objects.all().delete()

    for i in range(5):
        xabar_yozish(suhbat=suhbat, author=muammo.author, matn=f"Xabar {i}")

    assert (
        Notification.objects.filter(
            recipient=yechim.author, turi=BildirishnomaTuri.YANGI_XABAR
        ).count()
        == 1
    )


def test_OQILGANDAN_KEYIN_yangi_bildirishnoma_keladi():
    muammo, yechim, suhbat = _suhbat_ochish()
    Notification.objects.all().delete()
    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Birinchi")
    Notification.objects.filter(recipient=yechim.author).update(
        okilgan_at="2026-01-01T00:00:00Z"
    )

    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Ikkinchi")

    assert (
        Notification.objects.filter(
            recipient=yechim.author, turi=BildirishnomaTuri.YANGI_XABAR
        ).count()
        == 2
    )


def test_OZINGA_xabar_bildirishnomasi_kelmaydi():
    muammo, _, suhbat = _suhbat_ochish()
    Notification.objects.all().delete()

    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert Notification.objects.filter(recipient=muammo.author).count() == 0


# ===========================================================================
# 8. ⚠️ So'rov soni xabarlar soniga bog'liq EMAS
# ===========================================================================
def test_SUHBAT_sahifasi_XABAR_boshiga_sorov_QILMAYDI(client):
    """⚠️ `Xabar.korinadigan_nom` `suhbat` ga tayanadi — u ko'rinishda
    oldindan to'ldirilmasa har xabar bitta qo'shimcha so'rov qilardi."""
    muammo, yechim, suhbat = _suhbat_ochish()
    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Bir")
    client.force_login(yechim.author)
    manzil = suhbat.get_absolute_url()

    # ⚠️⚠️ KESH SO'ROV-SANOG'INI BUZADI (bu loyihada UCHINCHI marta).
    #    Sarlavhadagi o'qilmagan bildirishnomalar SANOG'I keshlanadi:
    #    birinchi so'rov uni HISOBLAYDI (+1 so'rov), ikkinchisi
    #    keshdan oladi (0). Ya'ni o'lchov kesh HOLATIGA bog'liq
    #    bo'lib qolardi va bu yerda o'sish YO'Q bo'lsa ham test
    #    yiqilardi. Yechim: keshni oldindan ILITISH.
    client.get(manzil)

    with CaptureQueriesContext(connection) as bitta:
        client.get(manzil)

    for i in range(6):
        xabar_yozish(suhbat=suhbat, author=muammo.author, matn=f"Yana {i}")
    with CaptureQueriesContext(connection) as yettita:
        client.get(manzil)

    assert len(yettita) == len(bitta)


def test_KONTAKT_SOROVI_bitta_yechimga_bitta():
    muammo, yechim = _qabul_qilingan()
    kontakt_sorash(solution=yechim, soragan=muammo.author)

    with pytest.raises(ValidationError):
        kontakt_sorash(solution=yechim, soragan=yechim.author)

    assert KontaktSorovi.objects.count() == 1


def test_XABAR_MODERATSIYA_qamrovida_ContentModel():
    """⚠️ `Xabar` `ContentModel` dan meros oladi — moderatsiya
    holati, yumshoq o'chirish va inqiroz bayrog'i BEPUL keladi."""
    assert hasattr(Xabar, "moderation_status")
    assert hasattr(Xabar, "deleted_at")
    assert hasattr(Xabar, "inqiroz_aniqlandi")
    assert hasattr(Xabar.objects, "visible")


# ===========================================================================
# 9. Uchidan-uchiga HTTP oqimi
# ===========================================================================
def test_TOLIQ_OQIM_sorovdan_xabargacha(client):
    """⚠️ Uchidan-uchiga: so'rov -> rozilik -> xabar -> yopish.

    Xizmat darajasidagi testlar mantiqni qoplaydi, lekin ko'rinishlar
    yo'lidagi ruxsat, yo'naltirish va forma nomlarini qoplamaydi —
    aynan shular jonli sahifada birinchi bo'lib buziladi.
    """
    muammo, yechim = _qabul_qilingan()

    # 1) Muammo muallifi so'rov yuboradi.
    client.force_login(muammo.author)
    javob = client.post(
        reverse("kontakt_sorov_yuborish", args=[yechim.pk]), follow=True
    )
    assert javob.status_code == 200
    sorov = KontaktSorovi.objects.get()
    assert sorov.holat == SorovHolati.KUTILMOQDA

    # 2) Yechim muallifi so'rovni ko'radi va qabul qiladi.
    client.force_login(yechim.author)
    sahifa = client.get(reverse("kontakt_sorovi", args=[sorov.pk]))
    assert sahifa.context["javob_berish_mumkinmi"] is True

    javob = client.post(
        reverse("kontakt_sorovi", args=[sorov.pk]), {"javob": "qabul"}, follow=True
    )
    assert javob.status_code == 200
    suhbat = Suhbat.objects.get()

    # 3) Xabar yozadi.
    client.post(suhbat.get_absolute_url(), {"matn": "Rahmat!"}, follow=True)
    assert suhbat.xabarlar.get().content == "Rahmat!"

    # 4) Suhbatni yopadi va endi yoza olmaydi.
    client.post(reverse("suhbatni_yopish", args=[suhbat.pk]), follow=True)
    suhbat.refresh_from_db()
    assert suhbat.yopiqmi is True

    client.post(suhbat.get_absolute_url(), {"matn": "Yana"}, follow=True)
    assert suhbat.xabarlar.count() == 1


def test_HTTP_rad_etish_SUHBATLARGA_yonaltiradi(client):
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    client.force_login(yechim.author)
    javob = client.post(reverse("kontakt_sorovi", args=[sorov.pk]), {"javob": "rad"})

    assert javob["Location"] == reverse("suhbatlar")
    sorov.refresh_from_db()
    assert sorov.holat == SorovHolati.RAD_ETILDI


def test_HTTP_BEGONA_sorovni_KORA_OLMAYDI(client):
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    client.force_login(TelegramUserFactory())

    assert client.get(reverse("kontakt_sorovi", args=[sorov.pk])).status_code == 404


def test_HTTP_QABUL_QILINMAGAN_yechimda_xato_KORSATILADI(client):
    """⚠️ Xizmat `ValidationError` beradi — ko'rinish uni 500 ga
    aylantirmasligi, foydalanuvchiga xabar ko'rsatishi kerak."""
    yechim = SolutionFactory()

    client.force_login(yechim.complaint.author)
    javob = client.post(
        reverse("kontakt_sorov_yuborish", args=[yechim.pk]), follow=True
    )

    assert javob.status_code == 200
    assert KontaktSorovi.objects.count() == 0


def test_HTTP_SORAGAN_odam_javob_TUGMASINI_KORMAYDI(client):
    muammo, yechim = _qabul_qilingan()
    sorov = kontakt_sorash(solution=yechim, soragan=muammo.author)

    client.force_login(muammo.author)
    sahifa = client.get(reverse("kontakt_sorovi", args=[sorov.pk]))

    assert sahifa.context["javob_berish_mumkinmi"] is False


def test_HTTP_BEGONA_suhbatni_YOPA_OLMAYDI(client):
    _, _, suhbat = _suhbat_ochish()

    client.force_login(TelegramUserFactory())
    javob = client.post(reverse("suhbatni_yopish", args=[suhbat.pk]))

    assert javob.status_code == 404
    suhbat.refresh_from_db()
    assert suhbat.yopiqmi is False


def test_OZ_XABARI_SIZ_deb_belgilanadi():
    """⚠️ Jonli tekshiruvda topilgan: anonim muallif O'Z xabarini
    «Anonim (muammo muallifi)» deb ko'rdi va bu chalg'ituvchi."""
    muammo, _, suhbat = _suhbat_ochish(anonim_muammo=True)
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert xabar.nom(muammo.author) == "Siz (anonim)"


def test_OCHIQ_muallifning_OZ_xabari_SIZ():
    muammo, _, suhbat = _suhbat_ochish()
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert xabar.nom(muammo.author) == "Siz"


def test_QARSHI_TOMON_uchun_ANONIM_qoladi():
    """⚠️⚠️ «Siz» yorlig'i FAQAT egasiga — qarshi tomon baribir
    «Anonim» ko'radi."""
    muammo, yechim, suhbat = _suhbat_ochish(anonim_muammo=True)
    xabar = xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    assert xabar.nom(yechim.author) == "Anonim (muammo muallifi)"
    assert muammo.author.display_name not in xabar.nom(yechim.author)


def test_SAHIFADA_SIZ_yorligi_korinadi(client):
    muammo, _, suhbat = _suhbat_ochish(anonim_muammo=True)
    xabar_yozish(suhbat=suhbat, author=muammo.author, matn="Salom")

    client.force_login(muammo.author)
    sahifa = client.get(suhbat.get_absolute_url()).content.decode()

    assert "Siz (anonim)" in sahifa
    assert "Anonim (muammo muallifi)" not in sahifa
