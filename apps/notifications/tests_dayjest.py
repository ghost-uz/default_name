"""Ekspertlarga «javobsiz savollar» dayjesti (D5-T5)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import ExpertProfileFactory, TelegramUserFactory
from apps.accounts.models import TasdiqHolati
from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import ComplaintStatus
from apps.notifications import dayjest
from apps.notifications.models import BildirishnomaTuri, Notification
from apps.notifications.tasks import dayjest_yuborish, telegram_yuborish
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

YUBORISH = "apps.notifications.tasks.xabar_yuborish"


def _savol(*, kategoriya, **kw):
    """Javobsiz, ochiq, ko'rinadigan savol."""
    kw.setdefault("status", ComplaintStatus.OPEN)
    return ComplaintFactory(category=kategoriya, **kw)


def _eskirtir(muammo, *, kun):
    """`created_at` — `auto_now_add`, ya'ni faqat `update()` bilan."""
    yangi = timezone.now() - timedelta(days=kun)
    type(muammo).objects.filter(pk=muammo.pk).update(created_at=yangi)
    muammo.refresh_from_db()
    return muammo


# ===========================================================================
# 1. ⚠️⚠️ Qabul mezoni — faqat ekspert sohasidagi savollar
# ===========================================================================
def test_FAQAT_EKSPERT_SOHASIDAGI_savollar():
    """⚠️⚠️ D5-T5 QABUL MEZONI.

    Boshqa sohadagi savol dayjestga TUSHMASLIGI kerak: mehnat huquqi
    advokatiga sog'liq savollarini yuborish uni ham, savol egasini ham
    aldaydi.
    """
    huquq = CategoryFactory(slug="huquq")
    sogliq = CategoryFactory(slug="sogliq")
    ekspert = ExpertProfileFactory(specialty=huquq)

    meniki = _savol(kategoriya=huquq)
    _savol(kategoriya=sogliq)

    natija = dayjest.dayjestlar()

    assert len(natija) == 1
    olingan_ekspert, savollar = natija[0]
    assert olingan_ekspert.pk == ekspert.pk
    assert [s.pk for s in savollar] == [meniki.pk]


def test_HAR_EKSPERT_OZ_sohasini_oladi():
    huquq = CategoryFactory(slug="huquq")
    moliya = CategoryFactory(slug="moliya")
    ExpertProfileFactory(specialty=huquq)
    ExpertProfileFactory(specialty=moliya)

    h_savol = _savol(kategoriya=huquq)
    m_savol = _savol(kategoriya=moliya)

    olingan = {
        e.specialty.slug: [s.pk for s in savollar]
        for e, savollar in dayjest.dayjestlar()
    }

    assert olingan == {"huquq": [h_savol.pk], "moliya": [m_savol.pk]}


# ===========================================================================
# 2. "Javobsiz" nimani anglatadi
# ===========================================================================
def test_JAVOB_BORI_chiqmaydi():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    javobsiz = _savol(kategoriya=kat)
    javobli = _savol(kategoriya=kat)
    SolutionFactory(complaint=javobli)

    _, savollar = dayjest.dayjestlar()[0]

    assert [s.pk for s in savollar] == [javobsiz.pk]


def test_YASHIRILGAN_yechim_JAVOB_EMAS():
    """⚠️ Yashirilgan yechim savol egasi uchun ham mavjud emas —
    demak savol hamon javobsiz."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    muammo = _savol(kategoriya=kat)
    SolutionFactory(complaint=muammo, moderation_status=ModerationStatus.HIDDEN)

    _, savollar = dayjest.dayjestlar()[0]

    assert [s.pk for s in savollar] == [muammo.pk]


def test_OCHIRILGAN_yechim_JAVOB_EMAS():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    muammo = _savol(kategoriya=kat)
    yechim = SolutionFactory(complaint=muammo)
    yechim.deleted_at = timezone.now()
    yechim.save(update_fields=["deleted_at"])

    _, savollar = dayjest.dayjestlar()[0]

    assert [s.pk for s in savollar] == [muammo.pk]


def test_YOPILGAN_savol_chiqmaydi():
    """⚠️ Muallif savolini yopgan bo'lsa javob KUTILMAYDI — u
    "javobsiz" bo'lsa ham ekspert vaqtini yeydi."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat, status=ComplaintStatus.CLOSED)

    assert dayjest.dayjestlar() == []


def test_YASHIRILGAN_savol_chiqmaydi():
    """⚠️ D2-T3: yashirilgan post dayjestga tushsa moderatsiyaning
    ma'nosi qolmaydi."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat, moderation_status=ModerationStatus.HIDDEN)

    assert dayjest.dayjestlar() == []


def test_INQIROZ_savoli_chiqmaydi():
    """⚠️⚠️ Sabab D5-T3 dan BOSHQA: bu yerda auditoriya bitta odam,
    ya'ni "kuchaytirish" dalili ishlamaydi.

    Haqiqiy sabab — ASBOB noto'g'ri: dayjest HAFTALIK va "ish navbati"
    shaklida keladi. Shoshilinch yordamga muhtoj odamni olti kun
    kutadigan navbatga qo'yish ikki marta xato.
    """
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat, inqiroz_aniqlandi=True)

    assert dayjest.dayjestlar() == []


# ===========================================================================
# 3. ⚠️ Tartib, oyna va chegara
# ===========================================================================
def test_ENG_ESKISI_BIRINCHI():
    """⚠️ Yangisidan boshlansa, band kategoriyada eski savollar HECH
    QACHON ro'yxatga tushmasdi — har hafta yangilari ustidan bosardi."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    yangi = _savol(kategoriya=kat)
    eski = _eskirtir(_savol(kategoriya=kat), kun=5)

    _, savollar = dayjest.dayjestlar()[0]

    assert [s.pk for s in savollar] == [eski.pk, yangi.pk]


def test_OYNADAN_ESKI_savol_chiqmaydi(settings):
    settings.DAYJEST_OYNA_KUNLARI = 14
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    _eskirtir(_savol(kategoriya=kat), kun=15)

    assert dayjest.dayjestlar() == []


def test_CHEGARA_hurmat_qilinadi(settings):
    settings.DAYJEST_SAVOL_SONI = 2
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    for _ in range(5):
        _savol(kategoriya=kat)

    _, savollar = dayjest.dayjestlar()[0]

    assert len(savollar) == 2


def test_TAKROR_ATAYLAB_bir_necha_hafta():
    """⚠️ Dayjest — yangiliklar lentasi emas, ISH NAVBATI: javobsiz
    savol keyingi haftada YANA chiqadi."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    muammo = _savol(kategoriya=kat)

    birinchi = dayjest.dayjestlar()[0][1]
    ikkinchi = dayjest.dayjestlar()[0][1]

    assert [s.pk for s in birinchi] == [s.pk for s in ikkinchi] == [muammo.pk]


# ===========================================================================
# 4. Kim dayjest oladi
# ===========================================================================
def test_TASDIQLANMAGAN_ekspert_olmaydi():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat, verification_status=TasdiqHolati.KUTILMOQDA)
    _savol(kategoriya=kat)

    assert dayjest.dayjestlar() == []


def test_TELEGRAMSIZ_ekspert_olmaydi():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat, user__telegram_id=None)
    _savol(kategoriya=kat)

    assert dayjest.dayjestlar() == []


def test_BOTNI_BLOKLAGAN_ekspert_olmaydi():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat, user__telegram_bloklandi=True)
    _savol(kategoriya=kat)

    assert dayjest.dayjestlar() == []


def test_BLOKLANGAN_ekspert_olmaydi():
    """⚠️ Bloklangan odam YOZA olmaydi (D2-T11) — dayjest uni bajarib
    bo'lmaydigan ishga chaqirardi."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat, user__is_banned=True)
    _savol(kategoriya=kat)

    assert dayjest.dayjestlar() == []


def test_BLOK_MUDDATI_OTGAN_ekspert_OLADI():
    """⚠️⚠️ `is_banned=False` tekshiruvi YETARLI EMAS: vaqtinchalik
    blok muddati o'tgan bo'lsa bayroq hali `True` turadi (uni fon
    vazifasi tozalaydi). Bu — `is_currently_banned` xossasining SQL
    shakli."""
    kat = CategoryFactory()
    ExpertProfileFactory(
        specialty=kat,
        user__is_banned=True,
        user__banned_until=timezone.now() - timedelta(days=1),
    )
    _savol(kategoriya=kat)

    assert len(dayjest.dayjestlar()) == 1


def test_PRO_TALAB_QILINMAYDI():
    """⚠️ PRO to'lov bilan bog'liq (D3-T5), dayjest esa yo'naltirish
    vositasi. Faqat to'lovchilarga yuborish taskning maqsadini —
    javobsiz savollarni kamaytirishni — buzardi."""
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    assert ekspert.pro_faolmi is False
    assert len(dayjest.dayjestlar()) == 1


def test_OCHIRILGAN_hisob_olmaydi():
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat, user__is_active=False)
    _savol(kategoriya=kat)

    assert dayjest.dayjestlar() == []


# ===========================================================================
# 5. ⚠️ Bo'sh dayjest yuborilmaydi
# ===========================================================================
def test_SAVOLSIZ_ekspertga_YUBORILMAYDI():
    """⚠️ "Bu hafta javobsiz savol yo'q" — aynan botdan chiqib ketishga
    olib keladigan shovqin (D5-T4)."""
    ExpertProfileFactory(specialty=CategoryFactory())

    assert dayjest.dayjestlar() == []
    assert dayjest_yuborish() == "0 ta"
    assert Notification.objects.count() == 0


def test_EKSPERTSIZ_platformada_yiqilmaydi():
    assert dayjest_yuborish() == "0 ta"


# ===========================================================================
# 6. ⚠️ N+1 — so'rov soni ekspertlar soniga bog'liq EMAS
# ===========================================================================
def test_SOROV_SONI_ekspertlar_soniga_BOGLIQ_EMAS():
    """⚠️ D1-T14 qoidasi. Har ekspert uchun alohida so'rov 100 ta
    ekspertda 100 ta so'rov degani."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    with CaptureQueriesContext(connection) as bitta:
        dayjest.dayjestlar()

    for _ in range(4):
        boshqa = CategoryFactory()
        ExpertProfileFactory(specialty=boshqa)
        _savol(kategoriya=boshqa)

    with CaptureQueriesContext(connection) as beshta:
        natija = dayjest.dayjestlar()

    assert len(natija) == 5
    assert len(beshta) == len(bitta) == 2


# ===========================================================================
# 7. Yozuv va Telegram xabari
# ===========================================================================
def test_YOZUV_yaratiladi_va_KATEGORIYANI_koradi():
    kat = CategoryFactory(name="Huquq", slug="huquq")
    ekspert = ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    yozuv = Notification.objects.get(recipient=ekspert.user)
    assert yozuv.turi == BildirishnomaTuri.DAYJEST
    # ⚠️ Dayjestni ODAM yubormaydi — "kimdir sizga yozdi" degan yolg'on
    #    taassurot bo'lmasin.
    assert yozuv.actor is None
    assert yozuv.matn == "Huquq sohasida javobsiz savollar"


def test_MANZIL_royxatga_olib_boradi():
    """⚠️ Bitta savolga emas: matn ko'plikda va bitta savolga tushirish
    qolganlarini ko'rinmas qilardi."""
    kat = CategoryFactory(slug="huquq")
    ekspert = ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    yozuv = Notification.objects.get(recipient=ekspert.user)
    assert yozuv.manzil == f"{reverse('feed')}?category=huquq&status=open"


def test_MATNDA_SANOQ_YOQ():
    """⚠️⚠️ M3 da uch marta qaytgan invariant: ko'rsatilgan raqam
    ko'rsatilgan ro'yxatga TENG bo'lsin. Ro'yxat JONLI, ya'ni har
    qanday saqlangan raqam ertaga yolg'on bo'lardi."""
    kat = CategoryFactory(name="Huquq")
    ekspert = ExpertProfileFactory(specialty=kat)
    for _ in range(3):
        _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    matn = Notification.objects.get(recipient=ekspert.user).matn
    assert not any(belgi.isdigit() for belgi in matn)


def test_XABARDA_HAVOLALAR_bor(django_capture_on_commit_callbacks):
    """⚠️ `on_commit` — Telegram vazifasi TRANZAKSIYA COMMIT bo'lgandan
    keyin navbatga tushadi (D5-T2). Testda uni ochiq ishga tushirish
    kerak, aks holda `xabar_yuborish` HECH QACHON chaqirilmaydi."""
    kat = CategoryFactory(name="Huquq")
    ekspert = ExpertProfileFactory(specialty=kat)
    muammo = _savol(kategoriya=kat)

    with (
        mock.patch(YUBORISH) as yuborish,
        django_capture_on_commit_callbacks(execute=True),
    ):
        dayjest_yuborish()

    matn = yuborish.call_args.kwargs["matn"]
    assert "Huquq" in matn
    assert muammo.title in matn
    assert muammo.get_absolute_url() in matn
    assert str(ekspert.user.telegram_id) == str(yuborish.call_args.kwargs["chat_id"])


def test_XABARDA_MUALLIF_YOQ(django_capture_on_commit_callbacks):
    """⚠️⚠️ Kanal (D5-T3) bilan bir xil qoida: ekspert SAVOLGA javob
    beradi, odamga emas. Matnda muallif bo'lmasa uni oshkor qilish
    ehtimoli ham yo'q."""
    kat = CategoryFactory()
    ExpertProfileFactory(specialty=kat)
    muallif = TelegramUserFactory(username="ochiq_muallif")
    _savol(kategoriya=kat, author=muallif, is_anonymous=False)

    with (
        mock.patch(YUBORISH) as yuborish,
        django_capture_on_commit_callbacks(execute=True),
    ):
        dayjest_yuborish()

    matn = yuborish.call_args.kwargs["matn"]
    assert "ochiq_muallif" not in matn
    assert muallif.display_name not in matn


def test_XABAR_YUBORISH_PAYTIDA_qayta_hisoblanadi():
    """⚠️⚠️ Ro'yxat SAQLANMAYDI. Jim soatlar (D5-T4) xabarni
    ertalabgacha kechiktiradi — saqlangan ro'yxat o'shanda allaqachon
    javob olgan savollarni ko'rsatardi."""
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    birinchi = _savol(kategoriya=kat)
    ikkinchi = _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()
    yozuv = Notification.objects.get(recipient=ekspert.user)

    # Yozuv yaratilgandan KEYIN birinchi savolga javob keldi.
    SolutionFactory(complaint=birinchi)

    with mock.patch(YUBORISH) as yuborish:
        telegram_yuborish(yozuv.pk)

    matn = yuborish.call_args.kwargs["matn"]
    assert ikkinchi.title in matn
    assert birinchi.title not in matn


def test_ROYXAT_BOSHAB_QOLSA_yuborilmaydi():
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    muammo = _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()
    yozuv = Notification.objects.get(recipient=ekspert.user)

    SolutionFactory(complaint=muammo)

    with mock.patch(YUBORISH) as yuborish:
        assert telegram_yuborish(yozuv.pk) == "bo'shab qoldi"

    yuborish.assert_not_called()


def test_EKSPERTLIK_BEKOR_QILINSA_yuborilmaydi():
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()
    yozuv = Notification.objects.get(recipient=ekspert.user)
    ekspert.delete()

    with mock.patch(YUBORISH) as yuborish:
        assert telegram_yuborish(yozuv.pk) == "bo'shab qoldi"

    yuborish.assert_not_called()


# ===========================================================================
# 8. ⚠️ D5-T4 infratuzilmasi meros olinadi
# ===========================================================================
def test_SOZLAMA_bilan_OCHIRILISHI_mumkin(django_capture_on_commit_callbacks):
    """⚠️ Dayjest D5-T4 sozlamalaridan o'tadi — yangi kod kerak emas."""
    from apps.notifications.models import BildirishnomaSozlamasi

    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    BildirishnomaSozlamasi.objects.create(
        user=ekspert.user, turlar={BildirishnomaTuri.DAYJEST.value: False}
    )
    _savol(kategoriya=kat)

    with (
        mock.patch(YUBORISH) as yuborish,
        django_capture_on_commit_callbacks(execute=True),
    ):
        dayjest_yuborish()

    yuborish.assert_not_called()
    # ⚠️ Yozuv baribir yaratiladi: sozlama YETKAZISHNI boshqaradi.
    assert Notification.objects.filter(recipient=ekspert.user).count() == 1


def test_STANDARTDA_YOQIQ():
    """⚠️⚠️ `MUHIM_TURLAR` ga ONGLI qo'shildi.

    D5-T4 dagi ehtiyotkorlik qoidasi HAJMGA qarshi edi; dayjest esa
    haftada bir marta va faqat tasdiqlangan ekspertga boradi. Standart
    holatda o'chiq bo'lsa, taskning maqsadi bajarilmasdi.
    """
    from apps.notifications.sozlama import MUHIM_TURLAR, standart_yoqilganmi

    assert BildirishnomaTuri.DAYJEST in MUHIM_TURLAR
    assert standart_yoqilganmi(BildirishnomaTuri.DAYJEST) is True


def test_MARKAZDA_qator_korinadi(client):
    kat = CategoryFactory(name="Huquq")
    ekspert = ExpertProfileFactory(specialty=kat)
    _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    client.force_login(ekspert.user)
    sahifa = client.get(reverse("bildirishnomalar")).content.decode()

    assert "Huquq sohasida javobsiz savollar" in sahifa


def test_MARKAZDA_BITTA_savol_sarlavhasi_KORSATILMAYDI(client):
    """⚠️⚠️ `complaint` dayjestda ro'yxatning BIRINCHI savoli.

    Uni quyi satrda chiqarish "dayjest = shu bitta savol" degan YOLG'ON
    taassurot berardi, matn esa ko'plikda. Jonli brauzer tekshiruvida
    aynan shunday ko'rindi va shablon tuzatildi.
    """
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    birinchi = _savol(kategoriya=kat)
    _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    client.force_login(ekspert.user)
    sahifa = client.get(reverse("bildirishnomalar")).content.decode()

    assert birinchi.title not in sahifa
    assert "Javob kutayotgan savollarni ko'rish" in sahifa


def _markaz_sorovlari(client, *, qatorlar: int) -> int:
    """Bildirishnomalar sahifasi N ta dayjest qatori bilan necha so'rov qiladi."""
    kat = CategoryFactory()
    ekspert = ExpertProfileFactory(specialty=kat)
    for _ in range(qatorlar):
        _savol(kategoriya=kat)

    with mock.patch(YUBORISH):
        dayjest_yuborish()

    # `dayjest_yuborish` bitta yozuv yaratadi; qolganini qo'lda qo'shamiz.
    yozuv = Notification.objects.get(recipient=ekspert.user)
    for muammo in dayjest.savollar_uchun(ekspert)[1:]:
        Notification.objects.create(
            recipient=ekspert.user, turi=yozuv.turi, complaint=muammo
        )
    assert Notification.objects.filter(recipient=ekspert.user).count() == qatorlar

    client.force_login(ekspert.user)
    with CaptureQueriesContext(connection) as sorovlar:
        javob = client.get(reverse("bildirishnomalar"))
    assert javob.status_code == 200
    return len(sorovlar)


def test_MARKAZDA_dayjest_qatori_QOSHIMCHA_sorov_QILMAYDI(client):
    """⚠️⚠️ Dayjest qatorining matni ham, manzili ham KATEGORIYAGA
    tayanadi — `complaint__category` JOIN'i bo'lmasa har qator +1
    so'rov qiladi.

    ⚠️ SHIFT EMAS, O'SISH tekshiriladi. Qotirilgan "15 dan kam" shakli
       bu regressiyani O'TKAZIB YUBORDI (empirik: JOIN'siz 5 qator = 11
       so'rov, ya'ni shiftdan past). So'rov soni qatorlar soniga
       BOG'LIQ EMASLIGI — mana shu haqiqiy invariant va uni bo'sh
       shift bilan aldab bo'lmaydi.
    """
    bitta = _markaz_sorovlari(client, qatorlar=1)
    beshta = _markaz_sorovlari(client, qatorlar=5)

    assert beshta == bitta
