"""To'lovlar — yozish amallari (D6-T1).

⚠️ OBUNA FAQAT SHU YERDA O'ZGARADI. D6-T2/T3 (Click/Payme) webhook'lari
   ham shu funksiyalarni chaqiradi — provayderga xos kod obuna
   mantiqini TAKRORLAMASIN, aks holda ikkita to'lov yo'li ikki xil
   qoida bo'yicha ishlardi va farqni faqat mijoz sezardi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.complaints.models import Complaint, ComplaintStatus

from .models import (
    BoostOrder,
    ObunaHolati,
    ObunaRejasi,
    Subscription,
    Tolov,
    TolovHolati,
    TolovMaqsadi,
    TolovSorovi,
)

log = logging.getLogger(__name__)


def _keshni_yangilash(user, obuna: Subscription) -> None:
    """Chaqiruvchi ushlab turgan `user` obyektidagi obunani yangilaydi.

    ⚠️⚠️ NEGA BU KERAK — JIM ESKIRISH.
       Bu funksiyalar obunani `select_for_update()` bilan QAYTA oladi,
       ya'ni ular chaqiruvchidagi `user.obuna` dan BOSHQA nusxani
       o'zgartiradi. Django teskari OneToOne ni obyektda keshlaydi
       (mavjud emasligini HAM keshlaydi), shuning uchun uzaytirishdan
       keyin O'SHA SO'ROV ichida `user.has_pro` hamon ESKI javobni
       berardi.

       Bu D6-T2/T3 da haqiqiy xatoga aylanardi: to'lov webhook'i
       obunani uzaytiradi, keyin o'sha so'rovda javob sahifasi
       "PRO faol emas" deb ko'rsatardi. Xato tasodifiy ko'rinardi —
       yangi so'rovda hammasi to'g'ri bo'lardi.

       Testlar buni ushladi (`test_MUDDATI_OTGAN_obuna_HOZIRDAN_boshlanadi`).
    """
    user.obuna = obuna


@transaction.atomic
def obunani_uzaytirish(
    *,
    user,
    kunlar: int | None = None,
    plan: str = ObunaRejasi.PRO,
) -> Subscription:
    """Obunani yaratadi yoki uzaytiradi.

    ⚠️⚠️ UZAYTIRISH QOLGAN MUDDAT USTIGA QO'SHILADI, `now` DAN EMAS.
       Muddati tugamagan obunani yangilagan odam qolgan kunlarini
       YO'QOTMASLIGI kerak — `now + 30` shakli aynan shuni qilardi va
       erta to'lagan mijozni jazolardi.

       Muddati ALLAQACHON o'tgan bo'lsa esa `now` dan boshlanadi:
       teskarisida uzoq tanaffusdan keyin qaytgan odam o'tmishga
       to'lagan bo'lardi.

    ⚠️ `select_for_update` — ikkita webhook bir vaqtda kelsa (D6-T2/T3
       da qayta urinish ODATIY hol) ikkalasi ham bir xil `expires_at`
       ni o'qib, bittasining uzaytirishi yo'qolardi.
    """
    kunlar = kunlar if kunlar is not None else settings.OBUNA_MUDDATI_KUN
    hozir = timezone.now()

    obuna = Subscription.objects.select_for_update().filter(user=user).first()
    if obuna is None:
        obuna = Subscription.objects.create(
            user=user,
            plan=plan,
            status=ObunaHolati.FAOL,
            started_at=hozir,
            expires_at=hozir + timedelta(days=kunlar),
        )
        log.info("obuna: yaratildi (user=%s, kun=%s)", user.pk, kunlar)
        _keshni_yangilash(user, obuna)
        return obuna

    asos = obuna.expires_at if obuna.expires_at > hozir else hozir
    obuna.expires_at = asos + timedelta(days=kunlar)
    obuna.plan = plan
    obuna.status = ObunaHolati.FAOL
    if asos == hozir:
        # Tanaffusdan keyin qaytdi — yangi davr boshlandi.
        obuna.started_at = hozir
    obuna.save(
        update_fields=["expires_at", "plan", "status", "started_at", "updated_at"]
    )
    log.info("obuna: uzaytirildi (user=%s, kun=%s)", user.pk, kunlar)
    _keshni_yangilash(user, obuna)
    return obuna


@transaction.atomic
def obunani_qisqartirish(*, user, kunlar: int) -> Subscription | None:
    """Obunani `kunlar` ga QISQARTIRADI — pul qaytarilganda (D6-T3).

    ⚠️⚠️ `obunani_uzaytirish` NING SIMMETRIK JUFTI. Uni "manfiy kun
       bilan uzaytirish" deb yozish mumkin edi, lekin o'sha
       funksiyadagi "muddati o'tgan bo'lsa `now` dan boshlanadi"
       qoidasi bu yerda TESKARI ishlardi: qaytarilgan to'lov
       obunani UZAYTIRIB yuborardi. Bu — bitta funksiyani ikki
       maqsadga moslashtirishning klassik narxi.

    ⚠️ MUDDAT O'TMISHGA TUSHISHI MUMKIN va bu TO'G'RI: pul
       qaytarilgan bo'lsa obuna ham tugagan bo'lishi kerak.
       `faolmi` buni o'zi hal qiladi (`expires_at > now`), ya'ni
       qo'shimcha "faolmi?" tekshiruvi kerak emas.

    ⚠️ `status` TEGILMAYDI: uni Celery vazifasi tozalaydi va
       `faolmi` baribir muddatni o'zi tekshiradi (D6-T1). Bu yerda
       uni qo'lda o'zgartirish ikkinchi haqiqat manbaini yasardi.
    """
    obuna = Subscription.objects.select_for_update().filter(user=user).first()
    if obuna is None:
        # To'lov bo'lgan, lekin obuna yo'q — mumkin emas, lekin
        # qaytarish yo'li shu sababdan yiqilmasin.
        log.warning("obuna: qisqartirish uchun qator yo'q (user=%s)", user.pk)
        return None

    obuna.expires_at = obuna.expires_at - timedelta(days=kunlar)
    obuna.save(update_fields=["expires_at", "updated_at"])
    log.info("obuna: qisqartirildi (user=%s, kun=%s)", user.pk, kunlar)
    _keshni_yangilash(user, obuna)
    return obuna


def avto_yangilashni_ozgartirish(*, user, yoqilsin: bool) -> Subscription | None:
    """«Bekor qilish» — avtomatik yangilashni o'chirish.

    ⚠️⚠️ OBUNA DARHOL TO'XTAMAYDI. Odam to'lagan muddati uchun xizmatni
       oladi; holati `FAOL` bo'lib qolaveradi va muddat tugagach
       vazifa uni `TUGAGAN` ga o'tkazadi.

       Darhol to'xtatish «bekor qilish» tugmasini JAZOGA aylantirardi:
       oyning boshida bekor qilgan odam yigirma to'qqiz kunini
       yo'qotardi va bu pulni qaytarish talabini keltirib chiqarardi.
    """
    obuna = Subscription.objects.filter(user=user).first()
    if obuna is None:
        return None

    obuna.auto_renew = yoqilsin
    obuna.save(update_fields=["auto_renew", "updated_at"])
    _keshni_yangilash(user, obuna)
    return obuna


def muddati_otganlarni_belgilash() -> int:
    """Muddati o'tgan FAOL obunalarni `TUGAGAN` deb belgilaydi.

    ⚠️⚠️ BU TOZALASH, HAQIQAT MANBAI EMAS. `Subscription.faolmi`
       muddatni HAR DOIM o'zi tekshiradi, ya'ni bu vazifa umuman
       ishlamasa ham hech kim bepul PRO olmaydi. Vazifaning ishi —
       hisobotlar va so'rovlar uchun holatni haqiqatga yaqin tutish.

    ⚠️ `update()` — `save()` har qator uchun so'rov qilardi va bu yerda
       hech qanday model mantiqi kerak emas.
    """
    return Subscription.objects.filter(
        status=ObunaHolati.FAOL, expires_at__lte=timezone.now()
    ).update(status=ObunaHolati.TUGAGAN, updated_at=timezone.now())


# ===========================================================================
# To'lov (D6-T2) — provayderdan MUSTAQIL yozish amallari
# ===========================================================================
# ⚠️⚠️ JURNALGA TUSHMAYDIGAN MAYDONLAR.
#    Qabul mezoni «barcha so'rovlar jurnalga yoziladi» — lekin IMZONING
#    O'ZI saqlanmaydi. U maxfiy kalit ishtirokidagi hash; qolgan
#    maydonlar shu qatorda yotgani uchun, bazani qo'lga kiritgan odamga
#    faqat kalitni oflayn tanlash qolardi (Click'da MD5 — aynan shunga
#    eng qulay algoritm).
#
#    O'rniga `imzo_togrimi` bayrogi qoladi. Nizoni hal qilishda kerak
#    bo'ladigan ma'lumot AYNAN SHU: "imzo o'tdimi?", "xom hash nima
#    edi?" emas.
#
#    ⚠️ Ro'yxat PROVAYDERDAN MUSTAQIL: D6-T3 (Payme) o'z maydonini shu
#       yerga qo'shadi va jurnal kodiga tegmaydi.
MAXFIY_MAYDONLAR = frozenset({"sign_string", "signature", "sign", "key"})


class Sabab(StrEnum):
    """To'lovni qabul qilmaslik sabablari — PROVAYDERDAN MUSTAQIL.

    ⚠️⚠️ NEGA CLICK KODLARI EMAS
       Click `-5`, Payme esa `-31050` yuboradi va ikkalasining
       ma'nolari bir-biriga TO'LIQ mos kelmaydi. Xizmat qatlami
       provayder kodini bilsa, D6-T3 da shu funksiyalarning ichida
       `if provayder == "payme"` tarmoqlari paydo bo'lardi — ya'ni
       to'lov mantiqi ikki marta yozilardi (D6-T1 aynan bundan
       ogohlantirgan).

       Kodga aylantirish — adapterning ishi (`views.SABAB_KODI`).
    """

    TOPILMADI = "topilmadi"
    SUMMA = "summa"
    ALLAQACHON = "allaqachon"
    TAYYORLANMAGAN = "tayyorlanmagan"
    BEKOR = "bekor"
    # ⚠️ D6-T3: buyurtmada BOSHQA tranzaksiya kutib turibdi.
    #    Payme'da bu xato (bir buyurtma — bir tranzaksiya), Click'da
    #    esa normal hol (odam qaytadan urinadi) — shuning uchun u
    #    sabab bo'lib qaytadi, xizmat qatlami esa qaysi biri
    #    ekanini BILMAYDI.
    BAND = "band"
    # ⚠️ D6-T4: buyurtma BOR, lekin u sotib oladigan narsani endi berib
    #    bo'lmaydi (masalan ko'tarilayotgan post shu orada yashirildi yoki
    #    yechildi). Tayyorlash bosqichida — PUL YECHILISHIDAN OLDIN — otiladi.
    YAROQSIZ = "yaroqsiz"


class TolovXatosi(Exception):
    """To'lov qabul qilinmadi. `sabab` javob kodiga aylantiriladi."""

    def __init__(self, sabab: Sabab) -> None:
        self.sabab = sabab
        super().__init__(sabab.value)


def _obunani_berish(tolov: Tolov) -> int:
    """PRO obunani uzaytiradi. Qaytaradi: BERILGAN KUN soni.

    ⚠️ `obunani_uzaytirish` QAYTA ISHLATILADI, nusxa olinmaydi: qolgan
       muddat ustiga qo'shish, tanaffusdan keyin `now` dan boshlash va
       `select_for_update` — hammasi allaqachon o'sha yerda va
       to'lovga xos sabab bilan yozilgan (D6-T1).

    ⚠️⚠️ KUN SONI QAYTARILADI va `Tolov.berilgan_kun` ga yoziladi.
       Pul qaytarilganda (D6-T3, Payme `-2`) AYNAN shuncha kun
       qaytarib olinadi. Sozlamadagi joriy qiymatga tayanish xato
       bo'lardi: muddat o'zgargan bo'lsa kompensatsiya berilgandan
       boshqa songa teng bo'lardi.
    """
    kunlar = settings.OBUNA_MUDDATI_KUN
    obunani_uzaytirish(user=tolov.user, kunlar=kunlar)
    return kunlar


def _obunani_qaytarib_olish(tolov: Tolov) -> None:
    """Pul qaytarildi — berilgan kunlar ham qaytarib olinadi.

    ⚠️⚠️ NEGA BU AVTOMATIK, D6-T2 DAGI QOIDADAN FARQLI
       D6-T2 da yozilgan: «to'langan buyurtma bekor qilinmaydi, pulni
       qaytarish qarori odamniki». U CLICK ning `error < 0` bilan
       kelgan ADASHGAN xabari haqida edi — Click'da "pulni qaytarish"
       degan amal umuman yo'q.

       Payme'ning `CancelTransaction` i esa bajarilgan tranzaksiyaga
       kelganda bu ANIQ VA OSHKORA ko'rsatma: pul mijozga qaytarildi
       (`state = -2`). Bunda obunani qoldirish "pulni qaytarib olib,
       xizmatni ham saqlab qolish" yo'lini ochardi.

    ⚠️ `berilgan_kun` YO'Q bo'lsa (D6-T3 dan OLDIN yaratilgan
       qatorlar) sozlamadagi qiymat ishlatiladi — bu taxmin, lekin
       hech narsa qaytarmaslikdan yaxshiroq va u jurnalga tushadi.
    """
    kunlar = tolov.berilgan_kun
    if kunlar is None:
        kunlar = settings.OBUNA_MUDDATI_KUN
        log.warning(
            "tolov: `berilgan_kun` yo'q, sozlama ishlatildi (id=%s, kun=%s)",
            tolov.pk,
            kunlar,
        )
    obunani_qisqartirish(user=tolov.user, kunlar=kunlar)


# ===========================================================================
# Boost — postni ko'tarish (D6-T4)
# ===========================================================================
def kotarib_bolmaslik_sababi(*, user, muammo: Complaint) -> str | None:
    """Postni ko'tarib BO'LMASLIK sababi; `None` — ko'tarish mumkin.

    ⚠️⚠️ BITTA FUNKSIYA, UCH ISTE'MOLCHI: batafsil sahifadagi tugma,
       sotib olish ko'rinishi va to'lovni TAYYORLASH bosqichi
       (`_boost_hali_yaroqlimi`). Uchinchisi eng muhimi: buyurtma
       yaratilgach post yashirilishi yoki yechilishi mumkin, pul esa hech
       narsa bermaydigan narsa uchun yechilmasligi kerak (D6-T2 dagi
       «PRO amalda hech narsa bermasdi» topilmasining o'zi).

    ⚠️ BAZAGA BORMAYDI — faqat qo'ldagi obyektlar. Batafsil sahifaning
       so'rov byudjeti (D1-T14) tugma uchun o'smasin.

    ⚠️ `deleted_at` ALOHIDA tekshiriladi: `is_publicly_visible` faqat
       moderatsiya holatiga qaraydi, FK orqali olingan post
       (`boost.complaint`) esa yumshoq o'chirilgan bo'lsa ham keladi.

    ⚠️⚠️ INQIROZ SABABI MATNDA AYTILMAYDI. D2-T6 siyosati: aniqlangan
       post muallifi HECH QANDAY ogohlantirish olmaydi. «Postingizda
       inqiroz belgisi bor» degan javob aynan shunday ogohlantirish
       bo'lardi — shuning uchun matn umumiy.
    """
    if muammo.author_id != user.pk:
        return "Faqat muallif o'z postini ko'tara oladi."
    if muammo.deleted_at is not None or not muammo.is_publicly_visible:
        return "Post hozir ommaga ko'rinmaydi."
    if muammo.status != ComplaintStatus.OPEN:
        return "Yechilgan yoki yopilgan savolni ko'tarib bo'lmaydi."
    if user.is_currently_banned:
        return "Cheklov davrida postni ko'tarib bo'lmaydi."
    # ⚠️ D2-T10: shartlar yangilangach qayta rozilik bermagan odam PULLIK
    #    xizmat ham sotib olmaydi — aks holda to'lov qaysi shartlar
    #    asosida qilingani noaniq qolardi.
    if not user.rozilik_bormi:
        return "Avval foydalanish shartlarining joriy versiyasini qabul qiling."
    if muammo.inqiroz_aniqlandi:
        return "Bu post uchun ko'tarish mavjud emas."
    return None


def kotarish_taklif_qilinadimi(*, user, muammo: Complaint) -> bool:
    """Batafsil sahifada «Ko'tarish» tugmasi chiqadimi. Bazaga bormaydi.

    ⚠️ To'lov tizimi ulanmagan bo'lsa tugma YO'Q: u odamni «ulanmagan»
       degan sahifaga olib borardi va u buni sayt nosozligi deb qabul
       qilardi (D6-T2 dagi `CLICK_YOQILGANMI` qarori).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if not (settings.CLICK_YOQILGANMI or settings.PAYME_YOQILGANMI):
        return False
    return kotarib_bolmaslik_sababi(user=user, muammo=muammo) is None


@transaction.atomic
def boost_buyurtmasi_yaratish(
    *, user, muammo: Complaint, provayder: str, summa: Decimal
) -> Tolov:
    """Ko'tarish buyurtmasi: `Tolov` + `BoostOrder` BITTA tranzaksiyada.

    ⚠️ Ikkalasi birga yoki hech biri: `BoostOrder` siz webhook qaysi
       postni ko'tarishni bilmasdi, pul esa yechilib bo'lardi.
    """
    tolov = tolov_yaratish(
        user=user, provayder=provayder, summa=summa, maqsad=TolovMaqsadi.BOOST
    )
    BoostOrder.objects.create(tolov=tolov, complaint=muammo)
    return tolov


def _boostni_berish(tolov: Tolov) -> int:
    """Ko'tarish oralig'ini belgilaydi. Qaytaradi: BERILGAN KUN soni.

    ⚠️⚠️ YANGI ORALIQ SHU POSTNING OXIRGI BOOSTI TUGAYDIGAN JOYDAN
       boshlanadi, `now` dan emas — `obunani_uzaytirish` bilan bir xil
       qoida: faol boost ustiga to'lagan odam qolgan soatlarini
       YO'QOTMASIN. Oldingisi tugagan bo'lsa — `now` dan.

    ⚠️ SHU POSTNING BARCHA boost qatorlari qulflanadi (`select_for_update`,
       `pk` tartibida — ikki tranzaksiya qulfni teskari tartibda olib
       bir-birini kutib qolmasin). Bir vaqtda yakunlangan ikki to'lov
       bir xil oxirni o'qisa, ikkalasi bir xil oraliqni olardi va
       ikkinchisi to'lagan kunini yo'qotardi. Qatorlar buyurtma paytida
       yaratilgani uchun qulflanadigan narsa BIRINCHI to'lovda ham bor.
    """
    complaint_id = (
        BoostOrder.objects.filter(tolov=tolov)
        .values_list("complaint_id", flat=True)
        .first()
    )
    if complaint_id is None:
        # To'lov bor, buyurtma yo'q — faqat post QATTIQ o'chirilganda
        # (CASCADE). Pul yechilgan: jurnalga tushadi, qaror odamniki.
        log.error("boost: buyurtma topilmadi (tolov=%s)", tolov.pk)
        return 0

    qatorlar = list(
        BoostOrder.objects.select_for_update()
        .filter(complaint_id=complaint_id)
        .order_by("pk")
    )
    boost = next(q for q in qatorlar if q.tolov_id == tolov.pk)

    kunlar = settings.BOOST_MUDDATI_KUN
    boshlanish = max(
        [timezone.now()]
        + [q.ends_at for q in qatorlar if q.pk != boost.pk and q.ends_at is not None]
    )
    boost.starts_at = boshlanish
    boost.ends_at = boshlanish + timedelta(days=kunlar)
    boost.save(update_fields=["starts_at", "ends_at", "updated_at"])
    log.info(
        "boost: berildi (tolov=%s, muammo=%s, %s -> %s)",
        tolov.pk,
        complaint_id,
        boost.starts_at,
        boost.ends_at,
    )
    return kunlar


def _boostni_qaytarib_olish(tolov: Tolov) -> None:
    """Pul qaytarildi — SHU to'lovning oralig'i yopiladi (D6-T3 juftligi).

    ⚠️ Oraliq `now` da KESILADI: faol bo'lsa darhol tugaydi, navbatda
       turgan bo'lsa (`starts_at` kelajakda) nol uzunlikka tushadi va
       hech qachon faollashmaydi. Qator O'CHIRILMAYDI — u tarix va
       nizoda «qachon ko'tarilgan edi?» savoliga javob beradi.

    ⚠️ Navbatdagi KEYINGI boostlar SURILMAYDI: ular o'z to'lovi bilan
       olingan va o'z vaqtida boshlanadi. Oradagi bo'shliq — qaytarilgan
       to'lovning to'g'ri oqibati; uni «tuzatish» keyingi to'lov sotib
       olgan vaqtni jimgina o'zgartirardi.
    """
    boost = BoostOrder.objects.select_for_update().filter(tolov=tolov).first()
    if boost is None or boost.starts_at is None or boost.ends_at is None:
        log.warning("boost: qaytarishda oraliq yo'q (tolov=%s)", tolov.pk)
        return

    yangi_oxir = max(boost.starts_at, min(boost.ends_at, timezone.now()))
    if yangi_oxir != boost.ends_at:
        boost.ends_at = yangi_oxir
        boost.save(update_fields=["ends_at", "updated_at"])
    log.info("boost: pul qaytarildi, oraliq yopildi (tolov=%s)", tolov.pk)


def _tekshiruv_shart_emas(tolov: Tolov) -> None:
    """Obuna uchun tayyorlash bosqichida qo'shimcha shart yo'q.

    ⚠️ Bo'sh funksiya lug'atda ATAYLAB turadi (`.get()` bilan tushirib
       qoldirilmaydi): yangi maqsad qo'shgan odam «pul yechilishidan
       oldin nimani tekshirish kerak?» savoliga javob berishga MAJBUR
       bo'lsin — javob «hech narsa» bo'lsa ham.
    """


def _boost_hali_yaroqlimi(tolov: Tolov) -> None:
    """Pul yechilishidan OLDIN: post hali ko'tarilishi mumkinmi.

    ⚠️ Sabab matni faqat JURNALGA tushadi. Provayderga semantik
       `YAROQSIZ` ketadi va u o'z kodiga aylantiriladi (`views`).
    """
    boost = BoostOrder.objects.select_related("complaint").filter(tolov=tolov).first()
    if boost is None:
        raise TolovXatosi(Sabab.YAROQSIZ)
    sabab = kotarib_bolmaslik_sababi(user=tolov.user, muammo=boost.complaint)
    if sabab is not None:
        log.warning("boost: tayyorlashda rad etildi (tolov=%s): %s", tolov.pk, sabab)
        raise TolovXatosi(Sabab.YAROQSIZ)


# ⚠️⚠️ KENGAYISH NUQTASI. Har maqsad UCHTA lug'atga bittadan funksiya
#    qo'shadi (D6-T4 boost aynan shunday qo'shildi) va Click/Payme
#    protokol kodiga UMUMAN tegmaydi.
#
# ⚠️ `dict`, `if/elif` EMAS: yangi maqsad qo'shilib, bajaruvchisi
#    unutilsa `KeyError` DARHOL chiqadi. `if/elif` zanjiri esa oxirida
#    jimgina `pass` bo'lib qolardi — ya'ni odam to'laydi, hech narsa
#    olmaydi va xato hech qayerda ko'rinmaydi.
# ⚠️ Annotatsiya SHART: `Tolov.maqsad` — `CharField`, ya'ni ish
#    vaqtida oddiy `str`. Annotatsiyasiz mypy kalit tipini
#    `TolovMaqsadi` deb chiqaradi va qidiruvni xato deb belgilaydi.
_MAQSAD_BAJARUVCHILARI: dict[str, Callable[[Tolov], int]] = {
    TolovMaqsadi.OBUNA: _obunani_berish,
    TolovMaqsadi.BOOST: _boostni_berish,
}

# ⚠️⚠️ HAR BERISHNING TESKARISI BO'LISHI SHART (D6-T3).
#    Payme pulni qaytara oladi, ya'ni "berilgan narsani qaytarib olish"
#    endi haqiqiy talab. Lug'atlar YONMA-YON turadi: yangi maqsad
#    qo'shgan odam qolganlarini ham to'ldirishi kerakligini KO'RADI.
#
#    Kalitlari bir xilligini test qo'riqlaydi — qaytarish unutilsa, pul
#    qaytarilgan xizmat ishlab qolaverardi va buni faqat mijoz payqardi.
_MAQSAD_BEKOR_QILUVCHILARI: dict[str, Callable[[Tolov], None]] = {
    TolovMaqsadi.OBUNA: _obunani_qaytarib_olish,
    TolovMaqsadi.BOOST: _boostni_qaytarib_olish,
}

# ⚠️⚠️ PUL YECHILISHIDAN OLDINGI TEKSHIRUV (D6-T4) — uchinchi lug'at.
#    Buyurtma yaratilishi bilan to'lov orasida daqiqalar (ba'zan soatlar)
#    o'tadi va shu orada sotib olinayotgan narsa yo'qolishi mumkin.
#    Tekshiruv Prepare / CreateTransaction / CheckPerformTransaction da
#    ishlaydi — u yerdagi xato provayderni pulni YECHMASDAN to'xtatadi.
#
#    Complete / Perform da ATAYLAB tekshirilmaydi: Prepare bilan orasi
#    soniyalar, xizmat berish yo'li esa sodda va idempotent qolishi
#    kerak. O'sha soniyalarda yashirilgan post baribir lentaga chiqmaydi
#    (`lenta_boostlari` ko'rinishni o'zi tekshiradi); pulni qaytarish
#    qarori — odamniki (DEPLOY.md 9.6).
_MAQSAD_TEKSHIRUVCHILARI: dict[str, Callable[[Tolov], None]] = {
    TolovMaqsadi.OBUNA: _tekshiruv_shart_emas,
    TolovMaqsadi.BOOST: _boost_hali_yaroqlimi,
}


def tolov_yaroqliligini_tekshirish(tolov: Tolov) -> None:
    """Maqsadga xos shartlar; buzilsa `TolovXatosi(Sabab.YAROQSIZ)`.

    ⚠️ Alohida OCHIQ funksiya: Payme'ning `CheckPerformTransaction` i
       `tolovni_tayyorlash` ni chaqirmaydi (u bazaga yozmaydi), lekin
       tekshiruv u yerda ham kerak — odam to'lov sahifasini aynan shu
       paytda ochib turibdi.
    """
    _MAQSAD_TEKSHIRUVCHILARI[tolov.maqsad](tolov)


def tolov_yaratish(
    *, user, provayder: str, summa: Decimal, maqsad: str = TolovMaqsadi.OBUNA
) -> Tolov:
    """Yangi buyurtma. Provayder sahifasiga yuborishdan OLDIN chaqiriladi.

    ⚠️ Summa SERVERDA hisoblanadi, formadan olinmaydi. Aks holda
       "PRO ni 1 so'mga sotib olish" so'rovni qo'lda yasash bilan
       ochilardi — bu turdagi eng klassik teshik.
    """
    tolov = Tolov.objects.create(
        user=user,
        provayder=provayder,
        summa=summa,
        maqsad=maqsad,
        holat=TolovHolati.YANGI,
    )
    log.info(
        "tolov: yaratildi (id=%s, user=%s, provayder=%s, summa=%s)",
        tolov.pk,
        user.pk,
        provayder,
        summa,
    )
    return tolov


def _tolovni_qulflab_olish(*, tolov_id: int, provayder: str, summa: Decimal) -> Tolov:
    """Qatorni `select_for_update` bilan oladi va summani tekshiradi.

    ⚠️ `provayder` ham filtrga kiradi: Click'ning so'rovi Payme
       buyurtmasini o'zgartira olmasin. Amalda bu bo'lmasligi kerak,
       lekin `merchant_trans_id` — oddiy ketma-ket son va uni taxmin
       qilish oson.
    """
    tolov = (
        Tolov.objects.select_for_update()
        .select_related("user")
        .filter(pk=tolov_id, provayder=provayder)
        .first()
    )
    if tolov is None:
        raise TolovXatosi(Sabab.TOPILMADI)

    # ⚠️ `Decimal` taqqoslash: "10000.00" == Decimal("10000") -> True.
    #    Shuning uchun provayder yuborgan shakl ahamiyatsiz.
    if tolov.summa != summa:
        raise TolovXatosi(Sabab.SUMMA)

    return tolov


@transaction.atomic
def tolovni_tayyorlash(
    *,
    tolov_id: int,
    provayder: str,
    summa: Decimal,
    provayder_trans_id: str,
    almashtirishga_ruxsat: bool = True,
) -> Tolov:
    """Prepare: "shunday buyurtma bormi, summa to'g'rimi?".

    ⚠️⚠️ TAKRORIY PREPARE — XATO EMAS. Click javobni olmasa qayta
       so'raydi va o'sha `click_trans_id` bilan keladi. Ikkinchi
       chaqiruv birinchisi bilan BIR XIL natija berishi kerak, aks
       holda tarmoq uzilishi to'lovni yo'qotardi.

    ⚠️ BOSHQA `click_trans_id` bilan qayta tayyorlashga RUXSAT.
       Odam Click sahifasida to'lovni tashlab ketib, keyin qaytadan
       boshlashi odatiy hol (sessiya muddati tugaydi). Yangi urinish
       yangi `click_trans_id` bilan keladi va uni rad etish odamni
       "to'lay olmaydigan" holatga tushirardi.

       Xavf yo'q: TO'LANGAN buyurtma bu yerga umuman yetib kelmaydi
       (pastdagi tekshiruv), ya'ni ikki marta pul yechilmaydi.

    ⚠️⚠️ `almashtirishga_ruxsat=False` — PAYME UCHUN (D6-T3).
       Payme'da bir buyurtmada bir vaqtda bitta tranzaksiya bo'ladi:
       kutayotgan tranzaksiya ustiga ikkinchisini yaratish
       `-31008` bilan rad etiladi. Click'da esa teskarisi TO'G'RI
       (yuqoriga qarang) — shuning uchun bu XULQ, sozlama emas, va
       uni chaqiruvchi ADAPTER tanlaydi.

    ⚠️⚠️ `tayyorlangan_at` FAQAT BIR MARTA yoziladi. Payme uni
       `create_time` sifatida qaytarib so'raydi va TAKRORIY so'rovda
       ham AYNAN o'sha qiymat kelishi shart. Har chaqiruvda yangilash
       "javob har safar boshqacha" degani bo'lardi va sandbox testi
       aynan shuni ushlaydi.
    """
    tolov = _tolovni_qulflab_olish(tolov_id=tolov_id, provayder=provayder, summa=summa)

    if tolov.holat == TolovHolati.TOLANDI:
        raise TolovXatosi(Sabab.ALLAQACHON)
    if tolov.holat == TolovHolati.BEKOR:
        raise TolovXatosi(Sabab.BEKOR)

    # ⚠️ D6-T4: maqsadga xos shart PUL YECHILISHIDAN OLDIN (masalan
    #    ko'tarilayotgan post shu orada yashirilgan). Takroriy Prepare ham
    #    tekshiriladi — holat o'zgargan bo'lsa ikkinchisi ham rad etilsin.
    tolov_yaroqliligini_tekshirish(tolov)

    boshqa_tranzaksiya = (
        tolov.holat == TolovHolati.TAYYOR
        and tolov.provayder_trans_id != provayder_trans_id
    )
    if boshqa_tranzaksiya and not almashtirishga_ruxsat:
        raise TolovXatosi(Sabab.BAND)

    tolov.holat = TolovHolati.TAYYOR
    tolov.provayder_trans_id = provayder_trans_id
    maydonlar = ["holat", "provayder_trans_id", "updated_at"]
    if tolov.tayyorlangan_at is None or boshqa_tranzaksiya:
        # Yangi tranzaksiya — yangi `create_time`. Takrorda esa
        # eskisi QOLADI (yuqoridagi izoh).
        tolov.tayyorlangan_at = timezone.now()
        maydonlar.append("tayyorlangan_at")
    _saqlash(tolov, maydonlar)
    log.info("tolov: tayyorlandi (id=%s, trans=%s)", tolov.pk, provayder_trans_id)
    return tolov


@transaction.atomic
def tolovni_yakunlash(
    *, tolov_id: int, provayder: str, summa: Decimal, provayder_trans_id: str
) -> tuple[Tolov, bool]:
    """Complete: pul yechildi. Qaytaradi: `(tolov, yangimi)`.

    ⚠️⚠️ QABUL MEZONI SHU YERDA: «bir xil transaction_id ikki marta
       kelsa ikkinchisi E'TIBORSIZ qoldiriladi».

       `yangimi=False` — takroriy so'rov. Obuna QAYTA UZAYTIRILMAYDI,
       lekin javob MUVAFFAQIYATLI qaytadi. Ikkinchisi muhim: takroriy
       so'rovga "xato" desak, Click to'lovni muvaffaqiyatsiz deb
       belgilab, pulni QAYTARIB yuborardi — odam esa xizmatni olgan
       bo'lardi.

    ⚠️⚠️ BOSHQA tranzaksiya to'langan buyurtmaga kelsa — `ALLAQACHON`.
       Bu takror EMAS, ikkinchi to'lov. Uni jimgina qabul qilish
       obunani ikki marta uzaytirardi.

       Ya'ni idempotentlik kaliti — `provayder_trans_id`, buyurtma
       raqami EMAS. Ikkalasini adashtirish bu integratsiyadagi eng
       qimmat xato bo'lardi.

    ⚠️ `TAYYOR` TALAB QILINADI: Prepare'siz kelgan Complete protokol
       buzilgani yoki so'rov soxtaligining belgisi.
    """
    tolov = _tolovni_qulflab_olish(tolov_id=tolov_id, provayder=provayder, summa=summa)

    if tolov.holat == TolovHolati.TOLANDI:
        if tolov.provayder_trans_id == provayder_trans_id:
            log.info("tolov: TAKRORIY complete e'tiborsiz (id=%s)", tolov.pk)
            return tolov, False
        raise TolovXatosi(Sabab.ALLAQACHON)

    if tolov.holat == TolovHolati.BEKOR:
        raise TolovXatosi(Sabab.BEKOR)
    if tolov.holat != TolovHolati.TAYYOR:
        raise TolovXatosi(Sabab.TAYYORLANMAGAN)

    tolov.holat = TolovHolati.TOLANDI
    tolov.provayder_trans_id = provayder_trans_id
    tolov.tolangan_at = timezone.now()
    _saqlash(tolov, ["holat", "provayder_trans_id", "tolangan_at", "updated_at"])

    # ⚠️ XIZMAT SHU YERDA, O'SHA TRANZAKSIYADA beriladi. Alohida
    #    Celery vazifasiga chiqarish "to'landi, lekin obuna yo'q"
    #    oynasini ochardi — navbat to'lib qolsa u oyna soatlab
    #    cho'zilishi mumkin.
    #
    # ⚠️ Nima berilgani YOZIB QO'YILADI: pul qaytarilganda aynan
    #    shuncha qaytarib olinadi (D6-T3).
    tolov.berilgan_kun = _MAQSAD_BAJARUVCHILARI[tolov.maqsad](tolov)
    _saqlash(tolov, ["berilgan_kun", "updated_at"])

    log.info(
        "tolov: YAKUNLANDI (id=%s, user=%s, maqsad=%s)",
        tolov.pk,
        tolov.user_id,
        tolov.maqsad,
    )
    return tolov, True


@transaction.atomic
def tolovni_bekor_qilish(
    *,
    tolov_id: int,
    provayder: str,
    izoh: str = "",
    bekor_kodi: int | None = None,
) -> Tolov | None:
    """Provayder to'lov amalga oshmaganini bildirdi.

    ⚠️ TO'LANGAN buyurtma bekor QILINMAYDI. Click `error < 0` bilan
       kelgan Complete so'rovi allaqachon to'langan buyurtmaga tegsa,
       bu Click tomondagi chalkashlik — biz obunani tortib olmaymiz,
       balki holatni o'zgarishsiz qoldiramiz. Pulni qaytarish qarori
       odamniki (admin), avtomat emas.
    """
    tolov = (
        Tolov.objects.select_for_update()
        .filter(pk=tolov_id, provayder=provayder)
        .first()
    )
    if tolov is None or tolov.holat == TolovHolati.TOLANDI:
        return tolov

    tolov.holat = TolovHolati.BEKOR
    tolov.izoh = izoh[:200]
    tolov.bekor_at = timezone.now()
    tolov.bekor_kodi = bekor_kodi
    _saqlash(tolov, ["holat", "izoh", "bekor_at", "bekor_kodi", "updated_at"])
    log.info("tolov: bekor qilindi (id=%s, izoh=%s)", tolov.pk, izoh)
    return tolov


@transaction.atomic
def tolovni_qaytarish(
    *, tolov_id: int, provayder: str, provayder_trans_id: str, bekor_kodi: int
) -> Tolov:
    """Pul QAYTARILDI: bajarilgan to'lov bekor qilindi (D6-T3).

    ⚠️⚠️ BU `tolovni_bekor_qilish` DAN BOSHQA AMAL. Birinchisi
       "to'lov amalga oshmadi" (pul umuman yechilmagan), bu esa
       "pul yechilgandi va qaytarildi". Ikkalasi bir funksiyaga
       siqilsa, xizmatni qaytarib olish sharti `if tolangan_at`
       bo'lib qolardi — ya'ni MUHIM qaror bir qatorlik shartga
       yashiringan bo'lardi.

    ⚠️⚠️ IDEMPOTENT: Payme `CancelTransaction` ni qayta yuboradi.
       Allaqachon qaytarilgan to'lov ikkinchi marta qaytarib
       OLINMAYDI — aks holda obuna ikki barobar qisqarardi.

    ⚠️ Hali bajarilmagan (TAYYOR) to'lov oddiy bekor bo'ladi va
       xizmat qaytarib olinmaydi — berilmagan narsani olib bo'lmaydi.
    """
    tolov = (
        Tolov.objects.select_for_update()
        .select_related("user")
        .filter(pk=tolov_id, provayder=provayder)
        .first()
    )
    if tolov is None:
        raise TolovXatosi(Sabab.TOPILMADI)

    if tolov.holat == TolovHolati.BEKOR:
        # Takroriy so'rov — hech narsa o'zgarmaydi.
        return tolov

    qaytarilsinmi = tolov.holat == TolovHolati.TOLANDI

    tolov.holat = TolovHolati.BEKOR
    tolov.bekor_at = timezone.now()
    tolov.bekor_kodi = bekor_kodi
    tolov.provayder_trans_id = provayder_trans_id
    _saqlash(
        tolov,
        ["holat", "bekor_at", "bekor_kodi", "provayder_trans_id", "updated_at"],
    )

    if qaytarilsinmi:
        _MAQSAD_BEKOR_QILUVCHILARI[tolov.maqsad](tolov)
        log.info(
            "tolov: PUL QAYTARILDI, xizmat qaytarib olindi (id=%s, user=%s, kod=%s)",
            tolov.pk,
            tolov.user_id,
            bekor_kodi,
        )
    else:
        log.info("tolov: bekor qilindi (id=%s, kod=%s)", tolov.pk, bekor_kodi)
    return tolov


def _saqlash(tolov: Tolov, maydonlar: list[str]) -> None:
    """`save(update_fields=...)`, lekin noyoblik buzilishini tarjima qiladi.

    ⚠️⚠️ NEGA SAVEPOINT KERAK
       `(provayder, provayder_trans_id)` noyobligi BAZA darajasida
       (`Tolov.Meta.constraints`). U buzilganda `IntegrityError`
       chiqadi va joriy tranzaksiyani "buzilgan" holatga tushiradi:
       shundan keyingi HAR QANDAY so'rov `TransactionManagementError`
       beradi — jurnalga yozish ham.

       Ichki `atomic()` savepoint qo'yadi va faqat SHU amalni orqaga
       qaytaradi, ya'ni tashqi tranzaksiya ishlashda davom etadi va
       biz tushunarli xato qaytara olamiz.

    ⚠️ Bu holat amalda faqat provayder bitta tranzaksiya raqamini
       ikkita buyurtmaga yuborsa yuz beradi. Imzo `merchant_trans_id`
       ni qamragani uchun uni tashqaridan yasab bo'lmaydi — lekin
       "bo'lmasligi kerak" degan taxmin ustiga pul mantiqini qurish
       to'g'ri emas.
    """
    try:
        with transaction.atomic():
            tolov.save(update_fields=maydonlar)
    except IntegrityError as xato:
        log.warning("tolov: tranzaksiya raqami takrorlandi (id=%s)", tolov.pk)
        raise TolovXatosi(Sabab.ALLAQACHON) from xato


def sorovni_jurnalga(
    *,
    provayder: str,
    amal: str,
    xom: dict,
    natija: int,
    javob: dict,
    tolov: Tolov | None = None,
    merchant_trans_id: str = "",
    provayder_trans_id: str = "",
    ip: str = "",
    imzo_togrimi: bool = False,
) -> TolovSorovi | None:
    """Kelgan so'rovni o'zgarmas jurnalga yozadi (qabul mezoni).

    ⚠️⚠️ HECH QACHON ISTISNO OTMASLIGI KERAK.
       Jurnal — YON ta'sir. Agar u yiqilsa (masalan JSON'ga
       sig'maydigan qiymat kelsa), to'lov javobini ham yiqitardi va
       Click so'rovni cheksiz qayta yuborardi. Ya'ni jurnalning
       nuqsoni PULNI to'xtatardi.

       Shuning uchun bu yerda keng `except` bor va u ONGLI qaror:
       yozilmagan jurnal — muammo, javobsiz webhook — falokat.

    ⚠️ Tranzaksiya ALOHIDA: `tolovni_yakunlash` yiqilib, uning
       tranzaksiyasi orqaga qaytganda ham jurnal QOLISHI kerak —
       aynan o'sha yiqilgan so'rov eng muhim dalil.
    """
    try:
        tozalangan = {k: v for k, v in xom.items() if k.lower() not in MAXFIY_MAYDONLAR}
        return TolovSorovi.objects.create(
            provayder=provayder,
            amal=amal,
            tolov=tolov,
            merchant_trans_id=merchant_trans_id[:64],
            provayder_trans_id=provayder_trans_id[:64],
            ip=ip[:45],
            imzo_togrimi=imzo_togrimi,
            natija=natija,
            xom=tozalangan,
            javob=javob,
        )
    except Exception:  # keng ushlash ONGLI — yuqoridagi izohga qarang
        log.exception("tolov jurnaliga yozib bo'lmadi (%s/%s)", provayder, amal)
        return None
