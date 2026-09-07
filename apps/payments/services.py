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

from .models import (
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


class TolovXatosi(Exception):
    """To'lov qabul qilinmadi. `sabab` javob kodiga aylantiriladi."""

    def __init__(self, sabab: Sabab) -> None:
        self.sabab = sabab
        super().__init__(sabab.value)


def _obunani_berish(tolov: Tolov) -> None:
    """PRO obunani uzaytiradi.

    ⚠️ `obunani_uzaytirish` QAYTA ISHLATILADI, nusxa olinmaydi: qolgan
       muddat ustiga qo'shish, tanaffusdan keyin `now` dan boshlash va
       `select_for_update` — hammasi allaqachon o'sha yerda va
       to'lovga xos sabab bilan yozilgan (D6-T1).
    """
    obunani_uzaytirish(user=tolov.user)


# ⚠️⚠️ KENGAYISH NUQTASI. D6-T4 (boost) shu lug'atga bitta qator
#    qo'shadi va Click/Payme kodiga UMUMAN tegmaydi.
#
# ⚠️ `dict`, `if/elif` EMAS: yangi maqsad qo'shilib, bajaruvchisi
#    unutilsa `KeyError` DARHOL chiqadi. `if/elif` zanjiri esa oxirida
#    jimgina `pass` bo'lib qolardi — ya'ni odam to'laydi, hech narsa
#    olmaydi va xato hech qayerda ko'rinmaydi.
# ⚠️ Annotatsiya SHART: `Tolov.maqsad` — `CharField`, ya'ni ish
#    vaqtida oddiy `str`. Annotatsiyasiz mypy kalit tipini
#    `TolovMaqsadi` deb chiqaradi va qidiruvni xato deb belgilaydi.
_MAQSAD_BAJARUVCHILARI: dict[str, Callable[[Tolov], None]] = {
    TolovMaqsadi.OBUNA: _obunani_berish,
}


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
    *, tolov_id: int, provayder: str, summa: Decimal, provayder_trans_id: str
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
    """
    tolov = _tolovni_qulflab_olish(tolov_id=tolov_id, provayder=provayder, summa=summa)

    if tolov.holat == TolovHolati.TOLANDI:
        raise TolovXatosi(Sabab.ALLAQACHON)
    if tolov.holat == TolovHolati.BEKOR:
        raise TolovXatosi(Sabab.BEKOR)

    tolov.holat = TolovHolati.TAYYOR
    tolov.provayder_trans_id = provayder_trans_id
    _saqlash(tolov, ["holat", "provayder_trans_id", "updated_at"])
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
    _MAQSAD_BAJARUVCHILARI[tolov.maqsad](tolov)

    log.info(
        "tolov: YAKUNLANDI (id=%s, user=%s, maqsad=%s)",
        tolov.pk,
        tolov.user_id,
        tolov.maqsad,
    )
    return tolov, True


@transaction.atomic
def tolovni_bekor_qilish(
    *, tolov_id: int, provayder: str, izoh: str = ""
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
    _saqlash(tolov, ["holat", "izoh", "updated_at"])
    log.info("tolov: bekor qilindi (id=%s, izoh=%s)", tolov.pk, izoh)
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
