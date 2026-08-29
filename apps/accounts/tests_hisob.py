"""Hisobni o'chirish va ma'lumot eksporti (D2-T8)."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    OCHIRILGAN_NOM,
    EksportHolati,
    MalumotEksporti,
    User,
)
from apps.accounts.services import eksport_soralgan, hisobni_ochirish
from apps.accounts.tasks import (
    eksport_malumoti,
    eksportni_tayyorlash,
    eskirgan_eksportlarni_ochirish,
)
from apps.common.models import VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint, ComplaintVote, SavedComplaint
from apps.gamification.models import KarmaEvent, KarmaReason
from apps.moderation.models import AuditAction, AuditLog, Report, ReportReason
from apps.solutions.factories import SolutionFactory
from apps.solutions.models import Solution

pytestmark = pytest.mark.django_db

HISOB = reverse("hisob")
OCHIRISH = reverse("hisob_ochirish")


# ===========================================================================
# ⭐ QABUL MEZONI: kontent qoladi, ism o'zgaradi
# ===========================================================================
def test_QABUL_MEZONI_kontent_QOLADI_ism_OZGARADI(user):
    """⭐ Qabul mezoni: "o'chirilgan foydalanuvchining kontenti qoladi,
    ismi 'O'chirilgan foydalanuvchi'ga aylanadi".

    Sabab task tavsifida: foydalanuvchi o'chganda uning 200 ta yechimi
    ham o'chsa, bu BOSHQA ODAMLARNING qiymatini yo'q qiladi.
    """
    muammo = ComplaintFactory(author=user, title="Mening dardim")
    yechim = SolutionFactory(author=user, content="Mening yechimim")

    hisobni_ochirish(user=user)

    muammo.refresh_from_db()
    yechim.refresh_from_db()
    user.refresh_from_db()

    assert muammo.title == "Mening dardim"
    assert yechim.content == "Mening yechimim"
    assert muammo.author == user  # bog'lanish uzilmaydi
    assert user.display_name == OCHIRILGAN_NOM


def test_QATOR_OCHIRILMAYDI(user):
    """⚠️ `User.delete()` chaqirilsa `author` `NULL` bo'lardi va bitta
    muhokamadagi ikki xil odam bir xil "muallifsiz" ko'rinardi —
    o'quvchi ularni bir odam deb o'ylashi mumkin."""
    pk = user.pk

    hisobni_ochirish(user=user)

    assert User.objects.filter(pk=pk).exists()


def test_IKKI_ochirilgan_hisob_BIR_XIL_KORINMAYDI(user_factory):
    """⭐⭐ Nega bitta umumiy "sentinel" foydalanuvchi EMAS.

    Umumiy sentinel bo'lsa, ikki xil odamning posti bitta muallifga
    tegishli bo'lib qolardi va suhbatda "o'zi bilan o'zi gaplashayotgan"
    odam taassuroti tug'ilardi.
    """
    birinchi, ikkinchi = user_factory(), user_factory()

    hisobni_ochirish(user=birinchi)
    hisobni_ochirish(user=ikkinchi)

    birinchi.refresh_from_db()
    ikkinchi.refresh_from_db()
    assert birinchi.pk != ikkinchi.pk
    assert birinchi.username != ikkinchi.username
    assert birinchi.display_name == ikkinchi.display_name == OCHIRILGAN_NOM


def test_SHAXSIY_malumot_tozalanadi(user):
    user.first_name = "Aziz"
    user.last_name = "Karimov"
    user.bio = "Men haqimda"
    user.email = "a@misol.uz"
    user.save()
    eski_username = user.username
    eski_telegram = user.telegram_id

    hisobni_ochirish(user=user)
    user.refresh_from_db()

    assert user.username != eski_username
    assert user.username.startswith("ochirilgan_")
    assert user.telegram_id is None != eski_telegram
    assert user.first_name == ""
    assert user.last_name == ""
    assert user.bio == ""
    assert user.email == ""
    assert user.is_active is False


def test_OVOZ_va_XATCHOP_ochiriladi(user):
    """⚠️ Ovoz va xatcho'p — SOF shaxsiy ma'lumot: ular odam nima
    o'qiganini va nimani ma'qullaganini ko'rsatadi."""
    muammo = ComplaintFactory()
    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=user,
        value=VoteValue.UP,
    )
    SavedComplaint.objects.create(user=user, complaint=muammo)

    hisobni_ochirish(user=user)

    assert ComplaintVote.objects.filter(user=user).count() == 0
    assert SavedComplaint.objects.filter(user=user).count() == 0


def test_SHIKOYAT_qoladi_lekin_SHIKOYATCHI_yoq(user):
    """Shikoyat moderator qarorining asosi (D2-T1), lekin kim yozgani
    shaxsiy ma'lumot."""
    hisobot = Report.objects.create(
        reporter=user, complaint=ComplaintFactory(), reason=ReportReason.SPAM
    )

    hisobni_ochirish(user=user)

    hisobot.refresh_from_db()
    assert hisobot.reporter is None


def test_ochirish_AUDIT_jurnaliga_tushadi(user):
    hisobni_ochirish(user=user)

    yozuv = AuditLog.objects.get(action=AuditAction.HISOB_OCHIRILDI)
    assert str(user.pk) in yozuv.obyekt


def test_jurnalda_ESKI_NOM_yozilmaydi(user):
    """⚠️ Jurnal ochiq (D2-T7). Eski nom yozilsa, anonimlashtirish
    ma'nosini yo'qotardi — nomni jurnaldan qayta topish mumkin
    bo'lardi."""
    eski = user.username

    hisobni_ochirish(user=user)

    yozuv = AuditLog.objects.get(action=AuditAction.HISOB_OCHIRILDI)
    assert eski not in json.dumps(
        {"o": yozuv.obyekt, "i": yozuv.izoh, "m": yozuv.malumot}, ensure_ascii=False
    )


def test_IKKI_MARTA_ochirish_zarar_qilmaydi(user):
    hisobni_ochirish(user=user)
    user.refresh_from_db()
    nom = user.username

    hisobni_ochirish(user=user)
    user.refresh_from_db()

    assert user.username == nom
    assert AuditLog.objects.filter(action=AuditAction.HISOB_OCHIRILDI).count() == 1


def test_ochirilgan_muallif_SAHIFADA_togri_korinadi(user, client):
    """Qabul mezoni interfeys darajasida."""
    muammo = ComplaintFactory(author=user, is_anonymous=False)
    SolutionFactory(complaint=muammo, author=user, is_anonymous=False)

    hisobni_ochirish(user=user)

    # ⚠️ Django `'` ni `&#x27;` ga aylantiradi (shablon O'ZGARUVCHIsi).
    from django.utils.html import escape

    matn = client.get(muammo.get_absolute_url()).content.decode()
    assert escape(OCHIRILGAN_NOM) in matn


# ===========================================================================
# Ko'rinishlar
# ===========================================================================
def test_hisob_sahifasi_KIRGANLAR_uchun(auth_client, anonymous_client):
    assert auth_client.get(HISOB).status_code == 200
    assert anonymous_client.get(HISOB).status_code == 302


def test_ochirish_TASDIQSIZ_bajarilmaydi(auth_client, user):
    javob = auth_client.post(OCHIRISH, {"tasdiq": "notogri"})

    user.refresh_from_db()
    assert javob.status_code == 200
    assert user.ochirilganmi is False


def test_ochirish_TASDIQ_bilan_bajariladi(auth_client, user):
    """⚠️ Tasdiqlash MATN bilan: qaytarib bo'lmaydigan amalni tasodifan
    bosib qo'yish mumkin bo'lmasin."""
    javob = auth_client.post(OCHIRISH, {"tasdiq": user.username}, follow=True)

    user.refresh_from_db()
    assert user.ochirilganmi is True
    assert javob.wsgi_request.user.is_anonymous, "sessiya yopilishi kerak"


def test_ochirish_sahifasi_NIMA_QOLISHINI_aytadi(auth_client):
    """⚠️ "Hammasi o'chadi" deb o'ylagan odam keyin o'z postlarini ko'rib
    aldangandek his qilmasligi kerak."""
    matn = auth_client.get(OCHIRISH).content.decode()

    # ⚠️ Bu yerda matn SHABLONDA yozilgan (o'zgaruvchi emas), ya'ni
    #    ekranlanmaydi — apostrof xom holda qoladi.
    assert "O'chadi" in matn
    assert "Qoladi" in matn
    assert OCHIRILGAN_NOM in matn


# ===========================================================================
# Eksport
# ===========================================================================
def test_eksport_MALUMOTI_ozining_kontentini_oladi(user):
    ComplaintFactory(author=user, title="Dardim")
    SolutionFactory(author=user, content="Yechimim")

    malumot = eksport_malumoti(user)

    assert malumot["profil"]["username"] == user.username
    assert [d["sarlavha"] for d in malumot["dardlar"]] == ["Dardim"]
    assert [y["matn"] for y in malumot["yechimlar"]] == ["Yechimim"]


def test_eksport_BOSHQALARNING_malumotini_OLMAYDI(user, user_factory):
    """⭐⭐ Vasvasa katta: "menga tegishli hamma narsa" deb postga
    kelgan shikoyatlarni va kim ovoz berganini qo'shib yuborish oson.

    Lekin bu BOSHQA odamlarning ma'lumoti bo'lardi va eksport ularning
    roziligisiz shaxsiy ma'lumot tarqatadigan quvurga aylanardi.
    """
    muammo = ComplaintFactory(author=user)
    begona = user_factory(username="begonaodam")
    Report.objects.create(reporter=begona, complaint=muammo, reason=ReportReason.SPAM)
    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=begona,
        value=VoteValue.UP,
    )

    xom = json.dumps(eksport_malumoti(user), ensure_ascii=False)

    assert "begonaodam" not in xom
    assert "shikoyat" not in xom.lower()


def test_eksportda_ANONIM_postlar_ham_bor(user):
    """Anonim post MUALLIF UCHUN anonim emas."""
    ComplaintFactory(author=user, is_anonymous=True, title="Anonim dardim")

    malumot = eksport_malumoti(user)

    assert malumot["dardlar"][0]["sarlavha"] == "Anonim dardim"
    assert malumot["dardlar"][0]["anonim"] is True


def test_eksportda_YASHIRILGAN_post_ham_bor(user):
    """⚠️ Yashirilgan post ham foydalanuvchiga tegishli: bu ommaviy
    ko'rinish emas, o'z ma'lumotining nusxasi."""
    from apps.common.models import ModerationStatus

    ComplaintFactory(
        author=user, title="Yashirilgan", moderation_status=ModerationStatus.HIDDEN
    )

    assert eksport_malumoti(user)["dardlar"][0]["sarlavha"] == "Yashirilgan"


def test_eksport_soralganda_NAVBATGA_qoyiladi(user):
    eksport = eksport_soralgan(user=user)

    assert eksport.holat == EksportHolati.NAVBATDA
    assert eksport.muddat > timezone.now()


def test_TAKRORIY_sorov_yangi_yozuv_YARATMAYDI(user):
    """Tugmani bir necha marta bosgan odam o'nlab vazifa yaratmasin."""
    birinchi = eksport_soralgan(user=user)
    ikkinchi = eksport_soralgan(user=user)

    assert birinchi.pk == ikkinchi.pk
    assert MalumotEksporti.objects.count() == 1


def test_vazifa_eksportni_TAYYORLAYDI(user):
    ComplaintFactory(author=user, title="Dardim")
    eksport = eksport_soralgan(user=user)

    eksportni_tayyorlash(eksport.pk)

    eksport.refresh_from_db()
    assert eksport.holat == EksportHolati.TAYYOR
    assert eksport.tayyor_at is not None
    assert eksport.malumot["dardlar"][0]["sarlavha"] == "Dardim"


def test_XATO_bolsa_holat_yoziladi(user, monkeypatch):
    """⚠️ Foydalanuvchi "so'rovim yo'qoldimi?" degan holatda
    qolmasin."""
    from apps.accounts import tasks

    monkeypatch.setattr(
        tasks, "eksport_malumoti", lambda u: (_ for _ in ()).throw(ValueError("buzuq"))
    )
    eksport = eksport_soralgan(user=user)

    eksportni_tayyorlash(eksport.pk)

    eksport.refresh_from_db()
    assert eksport.holat == EksportHolati.XATO
    assert "buzuq" in eksport.xato


def test_TAYYOR_eksport_yuklab_olinadi(auth_client, user):
    ComplaintFactory(author=user, title="Dardim")
    eksport = eksport_soralgan(user=user)
    eksportni_tayyorlash(eksport.pk)

    javob = auth_client.get(reverse("hisob_eksport_yuklash", args=[eksport.pk]))
    malumot = json.loads(javob.content)

    assert javob.status_code == 200
    assert "attachment" in javob["Content-Disposition"]
    assert malumot["dardlar"][0]["sarlavha"] == "Dardim"


def test_BOSHQANING_eksportini_yuklab_bolmaydi(auth_client, user_factory):
    """⭐ `get_object_or_404(pk=pk)` YETARLI EMAS: manzildagi raqamni
    o'zgartirgan odam BOSHQA odamning shaxsiy ma'lumotini olardi."""
    begona = user_factory()
    ComplaintFactory(author=begona)
    eksport = eksport_soralgan(user=begona)
    eksportni_tayyorlash(eksport.pk)

    javob = auth_client.get(reverse("hisob_eksport_yuklash", args=[eksport.pk]))

    assert javob.status_code == 404


def test_MUDDATI_OTGAN_eksport_berilmaydi(auth_client, user):
    eksport = eksport_soralgan(user=user)
    eksportni_tayyorlash(eksport.pk)
    MalumotEksporti.objects.filter(pk=eksport.pk).update(
        muddat=timezone.now() - timedelta(minutes=1)
    )

    javob = auth_client.get(reverse("hisob_eksport_yuklash", args=[eksport.pk]))

    assert javob.status_code == 302


def test_eskirgan_eksportlar_OCHIRILADI(user):
    """⚠️ Eksport ichida shaxsiy ma'lumot bor: "bir marta so'ralgan,
    keyin unutilgan" fayl bazada yillab turishi — ma'lumot sizishining
    eng oddiy yo'li."""
    yangi = eksport_soralgan(user=user)
    eski = MalumotEksporti.objects.create(
        user=user, muddat=timezone.now() - timedelta(days=1)
    )

    soni = eskirgan_eksportlarni_ochirish()

    assert soni == 1
    assert MalumotEksporti.objects.filter(pk=yangi.pk).exists()
    assert not MalumotEksporti.objects.filter(pk=eski.pk).exists()


def test_beat_jadvalida_tozalash_bor():
    """Vazifa yozilgan-u, rejaga qo'yilmagan bo'lsa u hech qachon
    ishlamaydi va buni hech narsa bildirmaydi."""
    from django.conf import settings

    vazifalar = {v["task"] for v in settings.CELERY_BEAT_SCHEDULE.values()}
    assert "apps.accounts.tasks.eskirgan_eksportlarni_ochirish" in vazifalar


# ===========================================================================
# Kontent butunligi
# ===========================================================================
def test_ochirishdan_keyin_KARMA_tarixi_qoladi(user):
    """Kontent hali turibdi, ya'ni ballar ham ma'noli."""
    KarmaEvent.objects.create(
        user=user, reason=KarmaReason.SOLUTION_ACCEPTED, points=15
    )

    hisobni_ochirish(user=user)

    assert KarmaEvent.objects.filter(user=user).count() == 1


def test_ochirishdan_keyin_kontent_LENTADA_qoladi(user, client):
    muammo = ComplaintFactory(author=user, title="Lentadagi dard")

    hisobni_ochirish(user=user)

    assert muammo in list(Complaint.objects.visible())
    assert "Lentadagi dard" in client.get("/").content.decode()


def test_ochirilgan_hisob_YOZA_OLMAYDI(user):
    hisobni_ochirish(user=user)
    user.refresh_from_db()

    assert user.can_write is False


def test_kontent_soni_ozgarmaydi(user):
    for _ in range(3):
        ComplaintFactory(author=user)
        SolutionFactory(author=user)

    hisobni_ochirish(user=user)

    assert Complaint.objects.filter(author=user).count() == 3
    assert Solution.objects.filter(author=user).count() == 3


def test_ochirilgan_hisob_KIRA_OLMAYDI(user):
    """`is_active=False` — Django autentifikatsiyasi rad etadi."""
    hisobni_ochirish(user=user)
    user.refresh_from_db()

    c = Client()
    c.force_login(user)
    javob = c.get(HISOB)

    assert javob.status_code == 302
