"""Schema.org QAPage — JSON-LD (D4-T6)."""

from __future__ import annotations

import json
import re

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.complaints.tasks import oxshash_kesh_kaliti
from apps.solutions.factories import SolutionFactory
from apps.solutions.services import accept_solution

pytestmark = pytest.mark.django_db


def jsonld(sahifa: str) -> dict | None:
    """Sahifadagi JSON-LD blokini lug'at qilib qaytaradi."""
    moslik = re.search(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', sahifa, re.DOTALL
    )
    return json.loads(moslik.group(1)) if moslik else None


def sahifa_matni(mijoz, muammo) -> str:
    javob = mijoz.get(muammo.get_absolute_url())
    assert javob.status_code == 200
    return javob.content.decode()


# ===========================================================================
# 1. Qachon chiqadi, qachon chiqmaydi
# ===========================================================================
def test_javobli_savolda_QAPage_bor(anonymous_client):
    muammo = ComplaintFactory(title="Ipoteka olish qiyinmi")
    SolutionFactory(complaint=muammo, content="Bank bilan qayta gaplashing.")

    ld = jsonld(sahifa_matni(anonymous_client, muammo))

    assert ld is not None
    assert ld["@context"] == "https://schema.org"
    assert ld["@type"] == "QAPage"
    assert ld["mainEntity"]["@type"] == "Question"


def test_JAVOBSIZ_savolda_QAPage_YOQ(anonymous_client):
    """⚠️⚠️ D4-T6 qabul mezoni: "Rich Results Test xatosiz o'tadi".

    Google `QAPage` uchun kamida bitta javob kutadi (`acceptedAnswer`
    yoki `suggestedAnswer`). Javobsiz savolda ular bo'lmaydi va test
    XATO beradi. Shuning uchun blok umuman chiqarilmaydi — sahifa
    baribir indekslanadi, faqat boyitilgan natija bo'lmaydi.
    """
    muammo = ComplaintFactory(title="Hali javob yo'q")

    assert jsonld(sahifa_matni(anonymous_client, muammo)) is None


def test_YASHIRILGAN_postda_QAPage_YOQ(user):
    """⚠️ Muallif o'z yashirilgan postini KO'RADI (D2-T3 istisnosi),
    lekin unga strukturaviy ma'lumot berish noto'g'ri: JSON-LD
    kontentni "e'lon qilingan" deb tasvirlaydi."""
    muammo = ComplaintFactory(
        title="Yashirin", author=user, moderation_status=ModerationStatus.HIDDEN
    )
    SolutionFactory(complaint=muammo, content="Javob matni")

    c = Client()
    c.force_login(user)

    assert jsonld(sahifa_matni(c, muammo)) is None


def test_YASHIRILGAN_yechim_QAPage_ga_TUSHMAYDI(anonymous_client):
    """⚠️⚠️ JSON-LD sahifada KO'RINMAYDI — ya'ni bu yerdagi sizib
    chiqishni odam sezmaydi, faqat Google ko'radi."""
    muammo = ComplaintFactory(title="Ochiq savol")
    SolutionFactory(complaint=muammo, content="KORINADIGAN javob")
    SolutionFactory(
        complaint=muammo,
        content="YASHIRIN javob matni",
        moderation_status=ModerationStatus.HIDDEN,
    )

    matn = sahifa_matni(anonymous_client, muammo)
    ld = jsonld(matn)

    assert "YASHIRIN javob" not in matn
    assert "YASHIRIN javob" not in json.dumps(ld, ensure_ascii=False)
    assert ld["mainEntity"]["answerCount"] == 1


# ===========================================================================
# 2. Mazmun
# ===========================================================================
def test_savol_maydonlari(anonymous_client):
    muammo = ComplaintFactory(
        title="Ipoteka olish qiyinmi", description="Bank uch marta rad etdi."
    )
    SolutionFactory(complaint=muammo, content="Javob")

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert savol["name"] == "Ipoteka olish qiyinmi"
    assert savol["text"] == "Bank uch marta rad etdi."
    assert savol["answerCount"] == 1
    assert "upvoteCount" in savol
    assert savol["dateCreated"].startswith(str(muammo.created_at.year))


def test_QABUL_QILINGAN_yechim_acceptedAnswer_da(anonymous_client, user):
    muammo = ComplaintFactory(title="Savol", author=user)
    qabul = SolutionFactory(complaint=muammo, content="Qabul qilingan javob")
    SolutionFactory(complaint=muammo, content="Boshqa javob")

    accept_solution(solution=qabul, by_user=user)

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert savol["acceptedAnswer"]["text"] == "Qabul qilingan javob"
    assert [y["text"] for y in savol["suggestedAnswer"]] == ["Boshqa javob"]


def test_qabul_qilinmagan_bolsa_faqat_suggestedAnswer(anonymous_client):
    muammo = ComplaintFactory(title="Savol")
    SolutionFactory(complaint=muammo, content="Birinchi")
    SolutionFactory(complaint=muammo, content="Ikkinchi")

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert "acceptedAnswer" not in savol
    assert len(savol["suggestedAnswer"]) == 2


def test_upvoteCount_ovozlarni_aks_ettiradi(anonymous_client, user, other_user):
    from apps.common.models import VoteValue
    from apps.common.voting import cast_vote
    from apps.complaints.models import ComplaintVote

    muammo = ComplaintFactory(title="Savol")
    SolutionFactory(complaint=muammo, content="Javob")
    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=other_user,
        value=VoteValue.UP,
    )

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert savol["upvoteCount"] == 1


def test_MANFIY_ball_nolga_keladi(anonymous_client, other_user):
    """⚠️ `upvoteCount` manfiy bo'la olmaydi — Google uni rad etadi."""
    from apps.common.models import VoteValue
    from apps.common.voting import cast_vote
    from apps.complaints.models import ComplaintVote

    muammo = ComplaintFactory(title="Savol")
    SolutionFactory(complaint=muammo, content="Javob")
    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=other_user,
        value=VoteValue.DOWN,
    )

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert savol["upvoteCount"] == 0


# ===========================================================================
# 3. ⚠️ Anonimlik — D1-T6 invariantining uchinchi joyi
# ===========================================================================
def test_ANONIM_savolda_muallif_YOQ(anonymous_client, user):
    """⚠️⚠️ Eng oson unutiladigan joy: JSON-LD sahifada KO'RINMAYDI,
    ya'ni anonimlik buzilganini foydalanuvchi ham, dasturchi ham
    sezmaydi — faqat Google indeksida qoladi."""
    muammo = ComplaintFactory(title="Anonim savol", author=user, is_anonymous=True)
    SolutionFactory(complaint=muammo, content="Javob")

    matn = sahifa_matni(anonymous_client, muammo)
    savol = jsonld(matn)["mainEntity"]

    assert "author" not in savol
    assert user.username not in json.dumps(jsonld(matn), ensure_ascii=False)


def test_ANONIM_yechimda_muallif_YOQ(anonymous_client, user, other_user):
    muammo = ComplaintFactory(title="Savol", author=user)
    SolutionFactory(
        complaint=muammo, content="Anonim javob", author=other_user, is_anonymous=True
    )

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]
    javob = savol["suggestedAnswer"][0]

    assert "author" not in javob
    assert other_user.username not in json.dumps(javob, ensure_ascii=False)


def test_ochiq_muallif_KORSATILADI(anonymous_client, user):
    muammo = ComplaintFactory(title="Ochiq savol", author=user)
    SolutionFactory(complaint=muammo, content="Javob")

    savol = jsonld(sahifa_matni(anonymous_client, muammo))["mainEntity"]

    assert savol["author"]["@type"] == "Person"
    assert savol["author"]["name"] == user.display_name


# ===========================================================================
# 4. ⚠️ Xavfsizlik
# ===========================================================================
def test_SKRIPT_TEGI_blokdan_CHIQA_OLMAYDI(anonymous_client):
    """⚠️⚠️ JSON ichidagi `</script>` ketma-ketligi brauzer uchun blokni
    SHU YERDA tugatadi va qolgan matn HTML bo'lib o'qiladi — ya'ni
    foydalanuvchi matni orqali teg kiritish mumkin bo'lardi.

    `<`, `>` va `&` kodlangani uchun bu yo'l butunlay yopiq.
    """
    muammo = ComplaintFactory(
        title="</script><img src=x onerror=alert(1)>",
        description="Yana bitta </script> shu yerda",
    )
    SolutionFactory(complaint=muammo, content="Javob </script> bilan")

    matn = sahifa_matni(anonymous_client, muammo)
    blok = re.search(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', matn, re.DOTALL
    ).group(1)

    assert "</script>" not in blok
    assert "\\u003C" in blok
    # Blok baribir yaroqli JSON bo'lib qolishi kerak.
    assert json.loads(blok)["mainEntity"]["name"].startswith("</script>")


def test_CSP_uchun_nonce_bor(anonymous_client):
    """⚠️ CSP `script-src` `<script>` elementiga TURIDAN QAT'I NAZAR
    qo'llanadi. Nonce'siz brauzer blokni rad etadi va Googlebot ham
    (u Chrome asosida ishlaydi) uni ko'rmasdi."""
    muammo = ComplaintFactory(title="Savol")
    SolutionFactory(complaint=muammo, content="Javob")

    matn = sahifa_matni(anonymous_client, muammo)
    moslik = re.search(r'<script type="application/ld\+json" nonce="([^"]+)"', matn)

    assert moslik, "JSON-LD blokida nonce yo'q"
    assert len(moslik.group(1)) > 10


def test_javob_URL_i_LANGARGA_olib_boradi(anonymous_client):
    """⚠️ Google javobga to'g'ridan-to'g'ri olib borishi kerak.

    Langar `templates/components/_solution.html` da (`id="yechim-<pk>"`)
    — ikkalasi bir-biriga bog'liq va bu test o'sha bog'lanishni
    qotiradi: langar nomi o'zgarsa JSON-LD havolasi hech qayerga
    olib bormay qoladi va buni hech kim sezmasdi.
    """
    muammo = ComplaintFactory(title="Savol")
    yechim = SolutionFactory(complaint=muammo, content="Javob")

    javob_matni = sahifa_matni(anonymous_client, muammo)
    savol = jsonld(javob_matni)["mainEntity"]

    assert savol["suggestedAnswer"][0]["url"].endswith(f"#yechim-{yechim.pk}")
    assert f'id="yechim-{yechim.pk}"' in javob_matni


def test_JSONLD_yechimlar_soniga_QARAB_sorov_QOSHMAYDI(anonymous_client):
    """⚠️⚠️ Birinchi versiyada `_javob()` `yechim.complaint` orqali yurgan
    va D1-T14 ning N+1 qo'riqchisi darhol yiqilgandi: `complaint_detail`
    yechimlarni `select_related("author")` bilan oladi, `complaint` esa
    unda YO'Q.

    Eng muhimi — regressiya BUTUNLAY BOSHQA MAVZUDAGI (SEO) o'zgarishdan
    keldi. Bu test o'sha bog'lanishni `schema.py` ning YONIDA ushlab
    turadi: umumiy N+1 testlari boshqa faylda va ular yiqilganda sabab
    darhol ko'rinmaydi.

    ⚠️ Qat'iy son EMAS, BOG'LIQLIK tekshiriladi (D1-T14 dagi bilan bir
       xil mantiq): 2 ta va 10 ta yechimda so'rov soni TENG bo'lishi
       kerak.
    """
    muammo = ComplaintFactory(title="Savol")
    for i in range(2):
        SolutionFactory(complaint=muammo, content=f"Javob {i}")

    # ⚠️ D4-T7 keshi ANIQ holatga qo'yiladi: usiz birinchi so'rov keshni
    #    to'ldiradi va ikkinchisi boshqa yo'ldan ketadi — o'lchov
    #    YECHIMLAR soniga emas, KESH holatiga bog'liq bo'lib qolardi.
    cache.set(oxshash_kesh_kaliti(muammo.pk), [], 300)

    with CaptureQueriesContext(connection) as ikkita:
        anonymous_client.get(muammo.get_absolute_url())

    for i in range(8):
        SolutionFactory(complaint=muammo, content=f"Qo'shimcha javob {i}")

    with CaptureQueriesContext(connection) as ontasi:
        javob = anonymous_client.get(muammo.get_absolute_url())

    assert jsonld(javob.content.decode())["mainEntity"]["answerCount"] == 10
    assert len(ontasi) == len(ikkita), (
        f"2 yechimda {len(ikkita)}, 10 yechimda {len(ontasi)} so'rov — "
        "JSON-LD har yechim uchun bog'lanish bo'ylab yuryaptimi?"
    )
