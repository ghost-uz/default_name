"""Ovoz berish mantig'i (D1-T5) — `ComplaintVote` va `SolutionVote` uchun umumiy.

⚠️ NEGA BU YERDA, MODEL METODI EMAS
   Ovoz berish IKKI jadvalga tegadi: ovoz qatori va maqsadning keshlangan
   sanoqchilari. Ular bitta tranzaksiyada o'zgarishi shart, aks holda
   sanoqchi haqiqatdan uzilib qoladi. Bu mantiq ikki modelda takrorlansa,
   bir kuni faqat bittasi tuzatiladi.

⚠️ `apps.common` BOSHQA ILOVALARNI IMPORT QILMAYDI
   Shuning uchun model klasslari PARAMETR sifatida beriladi. Bu bir oz
   ko'proq yozish, lekin `common` eng quyi qatlam bo'lib qolaveradi.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, connection, models, transaction

from apps.common.models import VotableModel, VoteModel, VoteValue


def _juftlikni_qulflash(*, user_pk: int, target_pk: int) -> None:
    """(odam, kontent) juftligini TRANZAKSIYA OXIRIGACHA qulflaydi (D7-T5).

    ⚠️⚠️ NEGA KERAK — O'LCHANGAN POYGA
       Ovozni qaytarib olish qatorni O'CHIRADI, ya'ni «qator bor / yo'q»
       holati tebranadi. Qulfsiz ikkita parallel so'rov shu tebranishga
       tushib qolardi: biri qatorni qulflab o'chiradi va commit qiladi,
       ikkinchisi esa uni kutib turib BO'SH natija oladi
       (`DoesNotExist` -> 500, bosilgan tugma esa yo'qoladi). 16 oqimli
       sinovda 60 bosishdan 48 tasi aynan shunday yiqilgan.

    ⚠️⚠️ NEGA QAYTA URINISH EMAS
       Chegaralangan qayta urinish KAFOLAT BERMAYDI, u faqat ehtimolni
       siljitadi: o'sha sinovda 5 ta urinish ham 20 ta so'rovga yetmadi
       (har raundda faqat bittasi yutadi, qolganlari qaytadan uriniladi).
       Qulf esa bir juftlikdagi amallarni QAT'IY KETMA-KET qiladi.

    ⚠️⚠️ NEGA KONTENT QATORI QULFLANMAYDI
       `SELECT ... FOR UPDATE` ni postga qo'yish ham poygani yopardi, lekin
       qulf tartibini TESKARI qilardi: hisobni o'chirish yo'li (D2-T8)
       avval ovoz qatorlarini, keyin sanoqchilarni qulflaydi. Bir-biriga
       teskari ikki tartib — deadlock uchun klassik retsept.

    ⚠️ DEADLOCK BO'LMAYDI: har tranzaksiya AYNAN BITTA advisory qulf oladi
       va uni ENG BIRINCHI bo'lib oladi — kutish sikli hosil bo'lmaydi.

    ⚠️ Kalit `user_pk` va `target_pk` dan yig'ilgan 63-bitli son.
       `ComplaintVote` va `SolutionVote` da bir xil juftlik uchrashi mumkin:
       u faqat ikkita aloqasiz amalni ketma-ket qilib qo'yadi, xato bermaydi.

    ⚠️ `pg_advisory_xact_lock` — PostgreSQL funksiyasi va u tranzaksiya
       tugashi bilan O'ZI bo'shaydi. Loyiha baribir faqat Postgres'da
       ishlaydi (GENERATED ustun, FTS, trigram).
    """
    kalit = ((user_pk & 0x7FFFFFFF) << 32) | (target_pk & 0xFFFFFFFF)
    with connection.cursor() as kursor:
        kursor.execute("SELECT pg_advisory_xact_lock(%s)", [kalit])


@dataclass(frozen=True)
class VoteResult:
    """Ovoz berishdan keyingi holat — HTMX javobini render qilish uchun.

    `value` — foydalanuvchining YANGI holati: `1`, `-1` yoki `None`
    (ovozini qaytarib oldi). Maketdagi `aria-pressed` shuni o'qiydi.
    """

    value: int | None
    upvotes: int
    downvotes: int
    score: int
    created: bool
    removed: bool
    switched: bool


def cast_vote(
    *,
    target: VotableModel,
    vote_model: type[VoteModel],
    target_field: str,
    user: Any,
    value: int,
) -> VoteResult:
    """Ovoz beradi, bekor qiladi yoki qarama-qarshisiga almashtiradi.

    Uch xil holat — hammasi BITTA tugma bosishidan kelib chiqadi:

        oldingi holat  bosildi   natija
        ─────────────  ────────  ──────────────────────────────
        ovoz yo'q      ↑         yangi ovoz          score +1
        ↑              ↑         ovoz bekor qilindi  score −1
        ↑              ↓         almashtirildi       score −2   ⚠️

    Oxirgi qatordagi "−2" tasodif emas: bitta ovoz `+1` dan `−1` ga
    o'tayotgani uchun farq ikki birlik. Bu D1-T5 qabul mezoni.

    ⚠️ POYGA HOLATI (race) — UCH QATLAMLI HIMOYA
       1. Yangi ovoz DARHOL `INSERT` qilinadi va noyoblik cheklovi
          buzilishiga TAYANILADI ("avval so'rab ko'rish" o'rniga). Ikki
          bir vaqtli so'rov "hozircha ovoz yo'q" deb ko'rishi mumkin,
          lekin ikkalasi ham INSERT qila olmaydi.
       2. Mavjud ovoz `select_for_update()` bilan QULFLANADI, ya'ni
          ikkinchi so'rov birinchisi tugagunicha kutadi va uning
          natijasini ko'radi.
       3. ⚠️⚠️ (ODAM, KONTENT) JUFTLIGI TRANZAKSIYA BOSHIDA QULFLANADI —
          `_juftlikni_qulflash()`. Shu bilan bir juftlikdagi barcha amallar
          QAT'IY KETMA-KET bo'ladi va quyidagi `.get()` hech qachon bo'sh
          qaytmaydi.

       Ichki `atomic()` — savepoint. Usiz `IntegrityError` butun
       tranzaksiyani yaroqsiz holga keltirardi va `except` bloki ichida
       hech qanday so'rov ishlamasdi.
    """
    if value not in (VoteValue.UP, VoteValue.DOWN):
        raise ValueError(f"Ovoz qiymati faqat +1 yoki -1 bo'ladi, berilgan: {value!r}")

    lookup: dict[str, Any] = {"user": user, target_field: target}

    with transaction.atomic():
        _juftlikni_qulflash(user_pk=user.pk, target_pk=target.pk)

        try:
            with transaction.atomic():
                vote_model._default_manager.create(**lookup, value=value)
            mavjud = None
        except IntegrityError:
            # ⚠️⚠️ `.get()` BU YERDA XAVFSIZ — FAQAT juftlik qulfi tufayli.
            #    Qulfsiz bu qator D7-T5 da o'lchangan poygani berardi: A
            #    so'rovi ovozni qulflab O'CHIRADI, B ning `INSERT` i noyoblik
            #    xatosini oladi va `select_for_update()` da A ni kutadi; A
            #    commit qilgach qator YO'Q (READ COMMITTED o'chirilganini
            #    natijadan tushiradi) va `.get()` `DoesNotExist` otardi —
            #    foydalanuvchiga 500, bosgan tugmasi esa yo'qolardi. 16 oqimli
            #    sinovda 60 bosishdan 48 tasi aynan shunday yiqilgan.
            mavjud = vote_model._default_manager.select_for_update().get(**lookup)

        if mavjud is None:
            delta_up = 1 if value == VoteValue.UP else 0
            delta_down = 1 if value == VoteValue.DOWN else 0
            yangi_holat, created, removed, switched = value, True, False, False

        elif mavjud.value == value:
            # Bir xil tugma ikkinchi marta — ovozni qaytarib olish.
            mavjud.delete()
            delta_up = -1 if value == VoteValue.UP else 0
            delta_down = -1 if value == VoteValue.DOWN else 0
            yangi_holat, created, removed, switched = None, False, True, False

        else:
            mavjud.value = value
            mavjud.save(update_fields=["value", "updated_at"])
            delta_up = 1 if value == VoteValue.UP else -1
            delta_down = -delta_up
            yangi_holat, created, removed, switched = value, False, False, True

        # ⚠️ `_base_manager` — `objects` EMAS.
        #    `Complaint.objects` yumshoq o'chirilganlarni filtrlaydi, ya'ni
        #    o'chirilgan postda `update()` HECH NIMANI o'zgartirmasdi va
        #    xato ham bermasdi — sanoqchi jimgina haqiqatdan uzilardi.
        #    (Bunday postga ovoz berish ko'rinish darajasida to'siladi;
        #    bu yerda esa xizmat halol bo'lishi kerak.)
        #
        # ⚠️ `PositiveIntegerField` manfiy qiymatda `IntegrityError` beradi.
        #    Bu ATAYLAB: sanoqchi noldan pastga tushayotgan bo'lsa, u
        #    allaqachon haqiqatdan uzilgan. Jim davom etgandan ko'ra
        #    baland yiqilgan yaxshi.
        target._meta.base_manager.filter(pk=target.pk).update(
            upvotes_cached=models.F("upvotes_cached") + delta_up,
            downvotes_cached=models.F("downvotes_cached") + delta_down,
        )

    # `score_cached` — GENERATED ustun, uni baza qayta hisoblab bo'ldi.
    target.refresh_from_db(
        fields=["upvotes_cached", "downvotes_cached", "score_cached"]
    )

    return VoteResult(
        value=yangi_holat,
        upvotes=target.upvotes_cached,
        downvotes=target.downvotes_cached,
        score=target.score_cached,
        created=created,
        removed=removed,
        switched=switched,
    )


def user_votes_for(
    *,
    vote_model: type[VoteModel],
    target_field: str,
    user: Any,
    # ⚠️ `Sequence`, `list` EMAS: `list` INVARIANT, ya'ni `list[Complaint]`
    #    `list[Model]` o'rniga o'tmaydi (chaqiruvchi ro'yxatga `Model`
    #    qo'shib yuborishi mumkin degan mulohaza). `Sequence` kovariant
    #    va faqat o'qish uchun — bu yerda aynan shu kerak.
    targets: Sequence[models.Model],
) -> dict[int, int]:
    """`{target_id: +1|-1}` — lentadagi barcha kartalar uchun BITTA so'rovda.

    ⚠️ D1-T14 (N+1) ning eng katta manbai aynan shu joy edi: har karta
       uchun "men ovoz berganmanmi?" deb alohida so'rash 20 ta kartada
       20 ta qo'shimcha so'rov degani.

    Kirmagan foydalanuvchi uchun bo'sh lug'at — so'rov umuman ketmaydi.
    """
    if not targets or not getattr(user, "is_authenticated", False):
        return {}

    juftlar = vote_model._default_manager.filter(
        user=user, **{f"{target_field}__in": targets}
    ).values_list(f"{target_field}_id", "value")
    return dict(juftlar)
