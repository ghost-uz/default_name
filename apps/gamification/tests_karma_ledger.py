"""Karma ledgeri — ovoz karmasi va kompensatsiya (D3-T1)."""

from __future__ import annotations

import pytest
from django.db import models

from apps.common.models import VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import ComplaintVote
from apps.gamification.models import KarmaEvent, KarmaReason
from apps.gamification.services import (
    karma_yoz,
    karmani_qayta_hisoblash,
    kontent_karmasini_qaytarish,
    kontent_karmasini_tiklash,
)
from apps.moderation.models import ModerationActionType, Report, ReportReason
from apps.moderation.services import qaror_qabul_qilish, qarorni_bekor_qilish
from apps.solutions.factories import SolutionFactory
from apps.solutions.services import yechimga_ovoz

pytestmark = pytest.mark.django_db


def ovoz(*, yechim, kim, qiymat=VoteValue.UP):
    return yechimga_ovoz(solution=yechim, user=kim, qiymat=qiymat)


def karma(user) -> int:
    user.refresh_from_db(fields=["karma_cached"])
    return user.karma_cached


# ===========================================================================
# ⭐ Ovoz karmasi
# ===========================================================================
def test_PLUS_ovoz_muallifga_karma_beradi(user, other_user):
    yechim = SolutionFactory(author=user)

    ovoz(yechim=yechim, kim=other_user)

    assert karma(user) == 2
    assert (
        KarmaEvent.objects.get(solution=yechim).reason == KarmaReason.SOLUTION_UPVOTED
    )


def test_MINUS_ovoz_karma_AYIRMAYDI(user, other_user):
    """⚠️⚠️ Foydalanuvchi qarori: `↓` `score_cached` ga ta'sir qiladi,
    lekin karmaga TEGMAYDI.

    Bu og'ir mavzular platformasi. Minus karma odamni, ayniqsa birinchi
    marta yozganini, butunlay jimitib qo'yardi. Sifatsiz javob ko'rinmay
    qoladi — bu yetarli; qoidabuzarlik esa moderatsiya ishi (D2-T11).
    """
    yechim = SolutionFactory(author=user)

    ovoz(yechim=yechim, kim=other_user, qiymat=VoteValue.DOWN)

    assert karma(user) == 0
    assert KarmaEvent.objects.count() == 0
    # ...lekin ovoz O'ZI hisoblandi (tartibga ta'sir qiladi):
    yechim.refresh_from_db()
    assert yechim.downvotes_cached == 1


def test_OZIGA_bergan_ovoz_karma_BERMAYDI(user):
    """⚠️⚠️ FERMA GUARD. Ovoz berishning o'zi to'silmagan (D1-T5 qarori),
    lekin karma berilsa: yechim yoz → o'zingga ovoz ber → +2, cheksiz."""
    yechim = SolutionFactory(author=user)

    ovoz(yechim=yechim, kim=user)

    assert karma(user) == 0
    assert KarmaEvent.objects.count() == 0


def test_DARDGA_ovoz_karma_BERMAYDI(user, other_user):
    """⚠️⚠️ Foydalanuvchi qarori: platformaning qiymati YORDAM BERISHDA.

    Dard yozish bepul bo'lsa, og'ir ahvoldagi odam "ball yig'ish" haqida
    o'ylamaydi — shunchaki so'raydi. Qarama-qarshi qaror dard yozib ball
    yig'ish yo'lini ochardi.
    """
    muammo = ComplaintFactory(author=user)

    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=other_user,
        value=VoteValue.UP,
    )

    assert karma(user) == 0
    assert KarmaEvent.objects.count() == 0


def test_ovoz_QAYTARIB_OLINSA_karma_ham_qaytadi(user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    ovoz(yechim=yechim, kim=other_user)  # bir xil tugma — bekor qilish

    assert karma(user) == 0
    assert KarmaEvent.objects.count() == 2, "yozuv O'CHIRILMAYDI, teskarisi yoziladi"
    assert KarmaEvent.objects.filter(reason=KarmaReason.SOLUTION_UPVOTE_OLINDI).exists()


def test_PLUSDAN_MINUSGA_almashtirilsa_karma_qaytadi(user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    ovoz(yechim=yechim, kim=other_user, qiymat=VoteValue.DOWN)

    assert karma(user) == 0


def test_MINUSDAN_PLUSGA_almashtirilsa_karma_beriladi(user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user, qiymat=VoteValue.DOWN)
    assert karma(user) == 0

    ovoz(yechim=yechim, kim=other_user)

    assert karma(user) == 2


def test_ovoz_TSIKLI_sof_natijasi_TOGRI(user, other_user):
    """⚠️ Ovoz ber → olib tashla → yana ber: sof natija bitta ovozniki.

    Jurnalda uchta yozuv qoladi (+2, −2, +2) — bu ATAYLAB: "nega karmam
    o'zgardi?" savoliga javob har bir qadam uchun ham kerak.
    """
    yechim = SolutionFactory(author=user)
    for _ in range(3):
        ovoz(yechim=yechim, kim=other_user)

    assert karma(user) == 2
    assert KarmaEvent.objects.count() == 3


def test_ANONIM_yechim_ham_ovoz_karmasini_oladi(user, other_user):
    """⚠️ Anonimlik faqat KO'RSATISHGA taalluqli (D1-T6), ballar esa
    haqiqiy hisobga. Aks holda anonim javob berish jazolanardi va
    odamlar eng og'ir mavzudagi javoblarni yozmay qo'yardi."""
    yechim = SolutionFactory(author=user, is_anonymous=True)

    ovoz(yechim=yechim, kim=other_user)

    assert karma(user) == 2


def test_MUALLIFSIZ_yechimda_ovoz_yiqilmaydi(other_user):
    """Hisobi o'chirilgan muallif (D2-T8) — `author=None`."""
    yechim = SolutionFactory(author=None)

    ovoz(yechim=yechim, kim=other_user)

    assert KarmaEvent.objects.count() == 0


# ===========================================================================
# ⭐ Kompensatsiya: kontent ko'rinmay qolganda
# ===========================================================================
def chora_kor(*, staff, yechim, turi=ModerationActionType.OLIB_TASHLASH):
    Report.objects.create(solution=yechim, reason=ReportReason.SPAM)
    return qaror_qabul_qilish(moderator=staff, target=yechim, action=turi)


def test_QABUL_MEZONI_kontent_olinsa_TESKARI_hodisa_yoziladi(staff, user, other_user):
    """⭐ Qabul mezoni: "kontent o'chirilsa teskari hodisa yoziladi"."""
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)
    assert karma(user) == 2

    chora_kor(staff=staff, yechim=yechim)

    assert karma(user) == 0
    kompensatsiya = KarmaEvent.objects.get(reason=KarmaReason.KONTENT_OLIB_TASHLANDI)
    assert kompensatsiya.points == -2
    # ⚠️ Eski yozuv O'CHIRILMAYDI — "nega karmam kamaydi?" javobsiz
    #    qolmasligi kerak.
    assert KarmaEvent.objects.filter(reason=KarmaReason.SOLUTION_UPVOTED).exists()


def test_QABUL_QILINGAN_yechim_olinsa_HAMMASI_qaytadi(staff, user, other_user):
    from apps.solutions.services import accept_solution

    muammo = ComplaintFactory(author=other_user)
    yechim = SolutionFactory(complaint=muammo, author=user)
    ovoz(yechim=yechim, kim=other_user)
    accept_solution(solution=yechim, by_user=other_user)
    assert karma(user) == 17  # 2 (ovoz) + 15 (qabul)

    chora_kor(staff=staff, yechim=yechim)

    assert karma(user) == 0


def test_YASHIRISH_ham_karmani_qaytaradi(staff, user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    chora_kor(staff=staff, yechim=yechim, turi=ModerationActionType.YASHIRISH)

    assert karma(user) == 0


def test_OGOHLANTIRISH_karmaga_TEGMAYDI(staff, user, other_user):
    """⚠️ Ogohlantirish kontentni ko'rinmas qilmaydi — demak u bergan
    ball ham o'z joyida qolishi kerak."""
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    chora_kor(staff=staff, yechim=yechim, turi=ModerationActionType.OGOHLANTIRISH)

    assert karma(user) == 2


def test_RAD_ETISH_karmaga_TEGMAYDI(staff, user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    chora_kor(staff=staff, yechim=yechim, turi=ModerationActionType.RAD_ETISH)

    assert karma(user) == 2


def test_qaytarish_IDEMPOTENT(user, other_user):
    """⚠️⚠️ Idempotentlik BAYROQ bilan emas, HISOB bilan: maqsad — shu
    yechim bo'yicha sof karma NOL. Ikkinchi chaqiruvda `jami` allaqachon
    nol va hech nima yozilmaydi."""
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)

    kontent_karmasini_qaytarish(solution=yechim)
    soni = KarmaEvent.objects.count()
    kontent_karmasini_qaytarish(solution=yechim)

    assert karma(user) == 0
    assert KarmaEvent.objects.count() == soni, "ikkinchi chaqiruv yozuv qo'shdi"


def test_CHORA_BEKOR_QILINSA_karma_qaytariladi(staff, user, other_user):
    """⭐ Moderatorning xatosi foydalanuvchining ballida abadiy
    qolmasligi kerak — D2-T11 dagi "bekor qilingan chora sanalmaydi"
    qoidasining karmadagi ko'rinishi."""
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)
    yozuv = chora_kor(staff=staff, yechim=yechim)
    assert karma(user) == 0

    qarorni_bekor_qilish(moderator=staff, chora=yozuv)

    assert karma(user) == 2
    assert KarmaEvent.objects.filter(reason=KarmaReason.KONTENT_TIKLANDI).exists()


def test_tiklash_IDEMPOTENT(user, other_user):
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)
    kontent_karmasini_qaytarish(solution=yechim)

    kontent_karmasini_tiklash(solution=yechim)
    soni = KarmaEvent.objects.count()
    kontent_karmasini_tiklash(solution=yechim)

    assert karma(user) == 2
    assert KarmaEvent.objects.count() == soni


def test_tiklashdan_KEYIN_ovoz_yana_ishlaydi(staff, user, other_user, user_factory):
    """⚠️ Kompensatsiya ovoz mantiqini SINDIRMASLIGI kerak."""
    yechim = SolutionFactory(author=user)
    ovoz(yechim=yechim, kim=other_user)
    yozuv = chora_kor(staff=staff, yechim=yechim)
    qarorni_bekor_qilish(moderator=staff, chora=yozuv)

    ovoz(yechim=yechim, kim=user_factory())

    assert karma(user) == 4


def test_karma_yoz_KOMPENSATSIYA_sababini_RAD_ETADI(user):
    """⚠️ Ball `KARMA_QIYMATLARI` dan olinadi; kompensatsiyaniki esa
    HISOBLANADI. Guard bo'lmasa kimdir bir kuni "tuzatish" uchun ularni
    lug'atga qo'shib qo'yardi va kompensatsiya jimgina noto'g'ri ball
    yozardi."""
    with pytest.raises(ValueError, match="kompensatsiya"):
        karma_yoz(user=user, reason=KarmaReason.KONTENT_OLIB_TASHLANDI)


# ===========================================================================
# ⭐ Qabul mezoni: karma_cached = SUM(KarmaEvent.points)
# ===========================================================================
def test_QABUL_MEZONI_kesh_MURAKKAB_oqimdan_keyin_ham_JURNALGA_teng(
    staff, user, other_user, user_factory
):
    """⭐ "karma_cached = SUM(KarmaEvent.points)".

    Oddiy holatda emas, ATAYLAB murakkab oqimdan keyin: ovozlar,
    almashtirishlar, qabul, chora, bekor qilish. Aynan shunday
    ketma-ketlikda kesh haqiqatdan uziladi.
    """
    from apps.solutions.services import accept_solution

    muammo = ComplaintFactory(author=other_user)
    yechim = SolutionFactory(complaint=muammo, author=user)

    ovoz(yechim=yechim, kim=other_user)
    ovoz(yechim=yechim, kim=other_user)  # bekor qilindi
    ovoz(yechim=yechim, kim=other_user)  # yana
    ovoz(yechim=yechim, kim=user_factory(), qiymat=VoteValue.DOWN)
    ovoz(yechim=yechim, kim=user_factory())
    accept_solution(solution=yechim, by_user=other_user)
    yozuv = chora_kor(staff=staff, yechim=yechim, turi=ModerationActionType.YASHIRISH)
    qarorni_bekor_qilish(moderator=staff, chora=yozuv)

    jurnal = KarmaEvent.objects.filter(user=user).aggregate(
        s=models.Sum("points", default=0)
    )["s"]

    assert karma(user) == jurnal
    assert karmani_qayta_hisoblash(user=user) == jurnal


# ===========================================================================
# Uchidan-uchiga: ovoz ko'rinishi
# ===========================================================================
def test_OVOZ_KORINISHI_karma_yozadi(auth_client, user, user_factory):
    """⚠️ Ko'rinish `cast_vote()` ni to'g'ridan-to'g'ri chaqirsa, karma
    jimgina o'tkazib yuborilardi. Bu test yagona kirish nuqtasini
    qo'riqlaydi."""
    muallif = user_factory()
    yechim = SolutionFactory(author=muallif)

    from django.urls import reverse

    javob = auth_client.post(reverse("yechim_ovoz", args=[yechim.pk]), {"qiymat": "1"})

    assert javob.status_code in (200, 302)
    assert karma(muallif) == 2
