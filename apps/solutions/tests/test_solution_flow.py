"""Yechim yozish va qabul qilish oqimi (D1-T10)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint, ComplaintStatus
from apps.gamification.models import KARMA_QIYMATLARI, KarmaEvent, KarmaReason
from apps.gamification.services import karmani_qayta_hisoblash
from apps.solutions.factories import ExpertSolutionFactory, SolutionFactory
from apps.solutions.models import Solution

pytestmark = pytest.mark.django_db

MATN = "Men ham shu holatdan o'tganman. Menga kredit tarixini tekshirish yordam berdi."


def yozish_url(muammo) -> str:
    return reverse("solution_create", args=[muammo.slug])


# ===========================================================================
# Yechim yozish
# ===========================================================================
def test_yechim_qoshiladi(auth_client, user):
    muammo = ComplaintFactory()

    javob = auth_client.post(yozish_url(muammo), {"content": MATN})

    assert javob.status_code == 302
    yechim = Solution.objects.get()
    assert yechim.author == user
    assert yechim.complaint == muammo


def test_yechim_SANOQCHINI_yangilaydi(auth_client):
    """⚠️ Sanoqchi signalda emas, xizmatda yangilanadi.

    Signal (`post_save`) jozibali ko'rinadi, lekin `bulk_create`,
    `loaddata` va ommaviy import'da ISHLAMAYDI — sanoqchi jimgina
    haqiqatdan uziladi.
    """
    muammo = ComplaintFactory()
    auth_client.post(yozish_url(muammo), {"content": MATN})

    muammo.refresh_from_db()
    assert muammo.solutions_count == 1


def test_ekspert_javobi_BAYROQNI_yoqadi(expert):
    """Lentadagi "Ekspert javob berdi" nishoni shu bayroqqa tayanadi."""
    from apps.solutions.services import yechim_yozish

    muammo = ComplaintFactory()
    assert muammo.has_expert_answer is False

    yechim_yozish(complaint=muammo, author=expert, content=MATN)

    muammo.refresh_from_db()
    assert muammo.has_expert_answer is True


def test_oddiy_javob_ekspert_bayrogini_YOQMAYDI(auth_client):
    muammo = ComplaintFactory()
    auth_client.post(yozish_url(muammo), {"content": MATN})

    muammo.refresh_from_db()
    assert muammo.has_expert_answer is False


def test_qisqa_yechim_rad_etiladi(auth_client):
    muammo = ComplaintFactory()

    javob = auth_client.post(yozish_url(muammo), {"content": "Qisqa"})

    assert javob.status_code == 200  # yo'naltirish YO'Q — sahifa qayta render
    assert Solution.objects.count() == 0


def test_xato_bolganda_YOZILGAN_MATN_qaytadi(auth_client):
    """⚠️ Uzun javobni qaytadan yozish — odamni ketkazadigan tajriba."""
    muammo = ComplaintFactory()
    # Yozilgan, lekin juda qisqa (30 belgidan kam) matn
    yozilgan = "Men shunday qilganman"

    javob = auth_client.post(yozish_url(muammo), {"content": yozilgan})

    assert javob.status_code == 200
    assert yozilgan in javob.content.decode()


def test_kirmagan_foydalanuvchi_yecha_OLMAYDI(client):
    muammo = ComplaintFactory()
    javob = client.post(yozish_url(muammo), {"content": MATN})

    assert javob.status_code == 302
    assert reverse("login") in javob["Location"]
    assert Solution.objects.count() == 0


def test_bloklangan_foydalanuvchi_yecha_OLMAYDI(banned_user):
    c = Client()
    c.force_login(banned_user)
    muammo = ComplaintFactory()

    javob = c.post(yozish_url(muammo), {"content": MATN})

    assert javob.status_code == 403
    assert Solution.objects.count() == 0


def test_YOPILGAN_muammoga_yechim_yozib_bolmaydi(auth_client):
    """`CLOSED` — muallif kutishni to'xtatdi."""
    muammo = ComplaintFactory(status=ComplaintStatus.CLOSED)

    javob = auth_client.post(yozish_url(muammo), {"content": MATN})

    assert javob.status_code == 403
    assert Solution.objects.count() == 0


def test_YECHILGAN_muammoga_yechim_yozish_MUMKIN(auth_client):
    """⚠️ Jonli sinovda topilgan qarama-qarshilik (D1-T10).

    `is_closed` `SOLVED` va `CLOSED` ni birlashtiradi va u bilan
    to'silganda o'z-o'ziga zid holat chiqardi: `accept_solution()`
    ATAYLAB boshqa yechimga o'tishni qo'llaydi (eskisidan karmani
    qaytarib), lekin yechim qabul qilingandan keyin yangi javob umuman
    kela olmasa, o'sha yo'lga deyarli tushib bo'lmasdi.

    Mahsulot nuqtai nazaridan ham: yaxshiroq javob keyinroq kelishi
    mumkin va muallif qabul qilishni unga o'tkazishi kerak.
    """
    muammo = ComplaintFactory(status=ComplaintStatus.SOLVED)

    javob = auth_client.post(yozish_url(muammo), {"content": MATN})

    assert javob.status_code == 302
    assert Solution.objects.count() == 1


def test_anonim_yechim(auth_client, user):
    muammo = ComplaintFactory()
    auth_client.post(yozish_url(muammo), {"content": MATN, "is_anonymous": "on"})

    yechim = Solution.objects.get()
    assert yechim.is_anonymous is True
    assert yechim.public_author is None
    assert yechim.author == user  # karma haqiqiy hisobga yoziladi


# ===========================================================================
# Qabul qilish (qabul mezonlari)
# ===========================================================================
def test_FAQAT_MUALLIF_qabul_qila_oladi(auth_client, user, other_user):
    """Qabul mezoni: "faqat muallif qabul qila oladi"."""
    muammo = ComplaintFactory(author=other_user)
    yechim = SolutionFactory(complaint=muammo)

    javob = auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    assert javob.status_code == 403
    yechim.refresh_from_db()
    assert yechim.is_accepted is False


def test_qabul_KARMA_HODISASINI_yaratadi(auth_client, user):
    """Qabul mezoni: "qabul qilish karma hodisasini yaratadi".

    ⚠️ Karma JURNAL (ledger), butun son emas: post o'chsa, qoida
       o'zgarsa yoki "nega menda 1340?" deb so'ralsa — javob jurnalda.
    """
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)
    javobchi = yechim.author

    auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    hodisa = KarmaEvent.objects.get()
    assert hodisa.user == javobchi
    assert hodisa.reason == KarmaReason.SOLUTION_ACCEPTED
    assert hodisa.points == KARMA_QIYMATLARI[KarmaReason.SOLUTION_ACCEPTED]
    assert hodisa.solution == yechim

    javobchi.refresh_from_db()
    assert javobchi.karma_cached == hodisa.points


def test_qabul_muammoni_YECHILGAN_qiladi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)

    auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    muammo.refresh_from_db()
    assert muammo.status == ComplaintStatus.SOLVED
    assert muammo.accepted_solution_id == yechim.pk


def test_takroriy_qabul_KARMANI_IKKILANTIRMAYDI(auth_client, user):
    """⚠️ Tugmani ikki marta bosish (yoki takroriy so'rov) ballarni
    ikkilantirardi — xizmat idempotent bo'lishi shart."""
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)

    auth_client.post(reverse("solution_accept", args=[yechim.pk]))
    auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    assert KarmaEvent.objects.count() == 1


def test_qabulni_bekor_qilish_TESKARI_YOZUV_qoshadi(auth_client, user):
    """⚠️ Yozuv O'CHIRILMAYDI, teskarisi qo'shiladi.

    Buxgalteriyadagi kabi: `+15`, `-15` = sof `0`. Bu "nega karmam
    kamaydi?" savoliga javob qoldiradi (D2-T7 audit).
    """
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)
    javobchi = yechim.author

    auth_client.post(reverse("solution_accept", args=[yechim.pk]))
    auth_client.post(reverse("solution_unaccept", args=[yechim.pk]))

    assert KarmaEvent.objects.count() == 2
    assert KarmaEvent.objects.filter(reason=KarmaReason.SOLUTION_ACCEPTED).exists()
    assert KarmaEvent.objects.filter(reason=KarmaReason.SOLUTION_UNACCEPTED).exists()

    javobchi.refresh_from_db()
    assert javobchi.karma_cached == 0

    muammo.refresh_from_db()
    assert muammo.status == ComplaintStatus.OPEN
    assert muammo.accepted_solution_id is None


def test_boshqa_yechimni_qabul_qilish_ESKISIDAN_karmani_qaytaradi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    birinchi = SolutionFactory(complaint=muammo)
    ikkinchi = SolutionFactory(complaint=muammo)

    auth_client.post(reverse("solution_accept", args=[birinchi.pk]))
    auth_client.post(reverse("solution_accept", args=[ikkinchi.pk]))

    birinchi.author.refresh_from_db()
    ikkinchi.author.refresh_from_db()
    assert birinchi.author.karma_cached == 0
    assert ikkinchi.author.karma_cached == 15

    birinchi.refresh_from_db()
    ikkinchi.refresh_from_db()
    assert birinchi.is_accepted is False
    assert ikkinchi.is_accepted is True


def test_anonim_yechimga_ham_KARMA_beriladi(auth_client, user):
    """⚠️ Anonimlik faqat KO'RSATISHGA taalluqli (D1-T6).

    Aks holda anonim javob berish jazolanardi va odamlar eng qimmatli
    (og'ir mavzudagi) javoblarni yozmay qo'yardi.
    """
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo, is_anonymous=True)

    auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    yechim.author.refresh_from_db()
    assert yechim.author.karma_cached == 15
    assert yechim.public_author is None


def test_karma_JURNALDAN_qayta_hisoblanadi(auth_client, user):
    """⚠️ Kesh haqiqatga mos ekanini isbotlaydigan yagona yo'l (D7-T3)."""
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)
    auth_client.post(reverse("solution_accept", args=[yechim.pk]))

    javobchi = yechim.author
    javobchi.karma_cached = 9999  # keshni ataylab buzamiz
    javobchi.save(update_fields=["karma_cached"])

    assert karmani_qayta_hisoblash(user=javobchi) == 15
    javobchi.refresh_from_db()
    assert javobchi.karma_cached == 15


def test_GET_bilan_qabul_qilib_bolmaydi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    yechim = SolutionFactory(complaint=muammo)
    assert (
        auth_client.get(reverse("solution_accept", args=[yechim.pk])).status_code == 405
    )


# ===========================================================================
# Batafsil sahifa
# ===========================================================================
def test_batafsil_sahifa_ochiladi(client):
    muammo = ComplaintFactory()
    javob = client.get(muammo.get_absolute_url())

    assert javob.status_code == 200
    assert muammo.title in javob.content.decode()


def test_qabul_qilingan_yechim_BIRINCHI_turadi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    SolutionFactory(complaint=muammo)
    ikkinchi = SolutionFactory(complaint=muammo)
    auth_client.post(reverse("solution_accept", args=[ikkinchi.pk]))

    javob = auth_client.get(muammo.get_absolute_url())
    assert javob.context["solutions"][0].pk == ikkinchi.pk


def test_korilganlar_sanogi_oshadi(client):
    muammo = ComplaintFactory()
    client.get(muammo.get_absolute_url())

    muammo.refresh_from_db()
    assert muammo.views_count == 1


def test_MUALLIFNING_ozi_korishi_SANALMAYDI(auth_client, user):
    """⚠️ Aks holda post yozgan odam uni bir necha marta ochib, sanoqni
    o'zi shishirib qo'yardi va ko'rsatkich ma'nosini yo'qotardi."""
    muammo = ComplaintFactory(author=user)
    auth_client.get(muammo.get_absolute_url())

    muammo.refresh_from_db()
    assert muammo.views_count == 0


def test_yashirilgan_post_MUALLIFGA_korinadi(auth_client, user):
    """⚠️ Posti yashirilgan foydalanuvchi buni BILISHI kerak, aks holda
    post "yo'qolgan" bo'lib ko'rinadi va ishonch yo'qoladi."""
    from apps.common.models import ModerationStatus

    muammo = ComplaintFactory(author=user, moderation_status=ModerationStatus.HIDDEN)
    javob = auth_client.get(muammo.get_absolute_url())

    assert javob.status_code == 200
    assert "hozircha ko'rinmaydi" in javob.content.decode()


def test_yashirilgan_post_BEGONAGA_404(client):
    from apps.common.models import ModerationStatus

    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    assert client.get(muammo.get_absolute_url()).status_code == 404


def test_qabul_tugmasi_FAQAT_MUALLIFGA_korinadi(auth_client, user, other_user):
    ozimniki = ComplaintFactory(author=user)
    SolutionFactory(complaint=ozimniki)
    begona = ComplaintFactory(author=other_user)
    SolutionFactory(complaint=begona)

    ozi = auth_client.get(ozimniki.get_absolute_url()).content.decode()
    boshqa = auth_client.get(begona.get_absolute_url()).content.decode()

    assert "Yechim sifatida qabul qilish" in ozi
    assert "Yechim sifatida qabul qilish" not in boshqa


def test_yashirilgan_yechim_sahifada_KORINMAYDI(client):
    from apps.common.models import ModerationStatus

    muammo = ComplaintFactory()
    korinadigan = SolutionFactory(complaint=muammo)
    SolutionFactory(complaint=muammo, moderation_status=ModerationStatus.HIDDEN)

    javob = client.get(muammo.get_absolute_url())
    assert [s.pk for s in javob.context["solutions"]] == [korinadigan.pk]


def test_batafsil_sahifa_sorov_soni_YECHIMLAR_SONIGA_BOGLIQ_EMAS(
    auth_client, user, django_assert_max_num_queries
):
    """⚠️ Har yechimda muallif, karma va "men ovoz berganmanmi?" bor."""
    muammo = ComplaintFactory(author=user)
    for _ in range(10):
        ExpertSolutionFactory(complaint=muammo)
    Complaint.objects.filter(pk=muammo.pk).update(solutions_count=10)

    with django_assert_max_num_queries(10):
        assert auth_client.get(muammo.get_absolute_url()).status_code == 200
