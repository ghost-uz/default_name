"""Tezlik cheklovi (D2-T4) — Redis'da, qo'shimcha paketsiz.

⚠️ NEGA `django-ratelimit` EMAS
   `requirements/base.txt` dagi qoida: "yangi paket qo'shishdan oldin
   savol bering — buni stdlib yoki Django bilan qilib bo'ladimi?".
   Bu yerda javob — ha: Django kesh API'sida atomik `incr()` bor va
   Redis backend uni server tomonida bajaradi. Butun mantiq ~100 qator.

⚠️ SOBIT OYNA (fixed window), silliq oyna EMAS
   Oyna raqami kalitning bir qismi (`hozir // oyna`), shuning uchun
   eskirish o'z-o'zidan bo'ladi va hech narsani tozalash kerak emas.

   Ma'lum kamchiligi bor: chegara oyna chegarasida IKKI BARAVAR
   o'tishi mumkin (oyna oxirida 30 ta + yangi oyna boshida yana 30 ta).
   Bu ataylab qabul qilingan — silliq oyna har so'rovda sanalgan
   ro'yxat yoki Lua skript talab qiladi, foyda esa shu holatda kichik:
   biz tanlagan chegaralar odam uchun juda bo'sh, skript uchun juda
   tor, ya'ni ikki baravar burst ham skriptni to'xtatadi.

⚠️ KESH ISHLAMASA — O'TKAZAMIZ (fail open)
   Redis o'chsa, cheklov ishlamaydi va so'rov o'tadi. Aks holda Redis
   nosozligi butun saytni "yozib bo'lmaydigan" holatga tushirardi.
   Tezlik cheklovi — YUMSHATISH chorasi, xavfsizlik chegarasi emas:
   haqiqiy himoya (o'z postiga ovoz bermaslik, noyoblik cheklovlari,
   moderatsiya) baza va xizmat qatlamida turadi.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

log = logging.getLogger(__name__)

# "30/m", "5/h", "100/2h" — son / [ko'paytiruvchi] birlik
CHEGARA_NAQSHI = re.compile(r"^(\d+)/(\d*)([smhd])$")
BIRLIKLAR = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# ⚠️ FAQAT YOZISH SO'ROVLARI SANALADI.
#    Aks holda formani ochish ham hisobga tushardi: "soatiga 5 ta post"
#    chegarasi formani 6 marta OCHGAN odamni bloklardi — va sabab
#    butunlay ko'rinmasdi ("hech narsa yozmadim-ku?").
SANALADIGAN_USULLAR = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Cheklov:
    soni: int
    oyna: int  # soniya

    @property
    def tavsif(self) -> str:
        """Foydalanuvchiga ko'rsatiladigan shakl."""
        if self.oyna % 3600 == 0:
            birlik = f"{self.oyna // 3600} soat" if self.oyna > 3600 else "soat"
        elif self.oyna % 60 == 0:
            birlik = f"{self.oyna // 60} daqiqa" if self.oyna > 60 else "daqiqa"
        else:
            birlik = f"{self.oyna} soniya"
        return f"{self.soni} marta / {birlik}"


def chegarani_oqish(matn: str) -> Cheklov:
    """`"30/m"` -> `Cheklov(30, 60)`; `"5/2h"` -> `Cheklov(5, 7200)`.

    Noto'g'ri yozilgan chegara JIM O'TMASLIGI kerak: sozlamadagi xato
    ("30/min") cheklovni butunlay o'chirib qo'yardi va buni hech kim
    payqamasdi.
    """
    m = CHEGARA_NAQSHI.match(matn.strip())
    if not m:
        raise ValueError(
            f"Chegara noto'g'ri: {matn!r}. Kutilgan shakl: '30/m', '5/h', '100/2h'."
        )
    soni, koeffitsiyent, birlik = m.groups()
    return Cheklov(soni=int(soni), oyna=int(koeffitsiyent or 1) * BIRLIKLAR[birlik])


def mijoz_ip(request: HttpRequest) -> str:
    """Mijozning haqiqiy IP manzili.

    ⚠️⚠️ BU YERDA IKKITA TESKARI XATO BOR — IKKALASI HAM JIM.

       1. `REMOTE_ADDR` ni ishlatish. Nginx ortida u HAR DOIM nginx'ning
          manzili bo'ladi — ya'ni butun sayt BITTA hisobga tushadi va
          IP cheklovi hammani birdan bloklaydi.

       2. `X-Forwarded-For` ga so'zsiz ishonish. Sarlavhani mijoz
          O'ZI yozadi: `X-Forwarded-For: 1.2.3.4` deb har so'rovda
          boshqa qiymat yuborsa, cheklov umuman ishlamaydi.

       Yechim — ISHONCHLI PROKSILAR SONI. Nginx `$proxy_add_x_forwarded_for`
       bilan ro'yxat OXIRIGA o'ziga ulangan manzilni qo'shadi, ya'ni bitta
       proksi bo'lsa mijoz IP'si oxirgi element. Undan chapdagilarni
       mijoz o'zi yozgan bo'lishi mumkin va ular E'TIBORGA OLINMAYDI.

       `ISHONCHLI_PROKSILAR_SONI = 0` (dev/test) -> `REMOTE_ADDR`.
       Prodda nginx bor -> `1`. CDN qo'shilsa -> `2`.
    """
    soni = getattr(settings, "ISHONCHLI_PROKSILAR_SONI", 0)
    if soni > 0:
        xom = request.META.get("HTTP_X_FORWARDED_FOR", "")
        qismlar = [q.strip() for q in xom.split(",") if q.strip()]
        if len(qismlar) >= soni:
            return qismlar[-soni]
        # Sarlavha kutilganidan qisqa — proksi sozlamasi noto'g'ri.
        # Ochiq qoldirgandan ko'ra `REMOTE_ADDR` ga qaytamiz.
        log.warning(
            "X-Forwarded-For kutilganidan qisqa (%s element, %s kutilgandi)",
            len(qismlar),
            soni,
        )
    return request.META.get("REMOTE_ADDR", "") or "nomalum"


def _oyna_oxirigacha(oyna: int) -> int:
    """Joriy oyna tugashiga necha soniya qoldi (`Retry-After` uchun)."""
    return oyna - int(time.time()) % oyna


def _sanash(*, nom: str, doira: str, belgi: str, cheklov: Cheklov) -> int:
    """Joriy oynadagi so'rovlar sonini oshiradi va qaytaradi."""
    oyna_raqami = int(time.time()) // cheklov.oyna
    kalit = f"tc:{nom}:{doira}:{belgi}:{oyna_raqami}"
    muddat = cheklov.oyna + 1

    # ⚠️ `add` + `incr` — poyga holatida ham TO'G'RI: `add` faqat kalit
    #    bo'lmaganda yozadi, `incr` esa Redis'da atomik. Ikki so'rov bir
    #    vaqtda kelsa, biri `add` qiladi, ikkalasi ham `incr` qiladi -> 2.
    cache.add(kalit, 0, timeout=muddat)
    try:
        return cache.incr(kalit)
    except ValueError:
        # Kalit `add` bilan `incr` orasida eskirdi (oyna chegarasi).
        cache.set(kalit, 1, timeout=muddat)
        return 1


def cheklovlarni_olish(nom: str) -> dict[str, Cheklov]:
    """Sozlamadagi chegaralar — `{"foydalanuvchi": Cheklov, "ip": Cheklov}`.

    ⚠️ Sozlama HAR CHAQIRUVDA o'qiladi, modul yuklanganda emas —
       `@override_settings` bilan test yozish mumkin bo'lsin.
    """
    xom = settings.TEZLIK_CHEKLOVLARI.get(nom)
    if xom is None:
        raise ValueError(
            f"`TEZLIK_CHEKLOVLARI` da {nom!r} yo'q. "
            "Chegaralar sozlamada bo'lishi kerak (D2-T4 qabul mezoni)."
        )
    return {doira: chegarani_oqish(qiymat) for doira, qiymat in xom.items()}


def _429(request: HttpRequest, *, cheklov: Cheklov, qolgan: int) -> HttpResponse:
    """Chegara oshgandagi javob (D2-T4 qabul mezoni: 429 + tushunarli xabar).

    ⚠️ HTMX 2xx BO'LMAGAN JAVOBNI DOM'GA QO'YMAYDI.
       Shuning uchun HTMX so'roviga qisqa MATN qaytariladi va uni
       `app.js` dagi `htmx:responseError` ishlovchisi toast qilib
       ko'rsatadi. Usiz ovoz tugmasi bosilardi-yu, HECH NARSA
       bo'lmasdi — foydalanuvchi uchun bu "sayt buzilgan" degani.
    """
    xabar = (
        f"Juda tez yuboryapsiz. Chegara: {cheklov.tavsif}. "
        f"{qolgan} soniyadan keyin qayta urinib ko'ring."
    )
    if request.headers.get("HX-Request") == "true":
        javob = HttpResponse(
            xabar, status=429, content_type="text/plain; charset=utf-8"
        )
    else:
        javob = render(
            request, "429.html", {"xabar": xabar, "qolgan": qolgan}, status=429
        )
    javob["Retry-After"] = str(qolgan)
    return javob


def tezlik_cheklovi(nom: str) -> Callable:
    """`settings.TEZLIK_CHEKLOVLARI[nom]` bo'yicha cheklaydi.

    Ikki doira birdan qo'llanadi:

      · `foydalanuvchi` — kirgan foydalanuvchi uchun (`pk` bo'yicha).
        Bu ASOSIY cheklov va u TOR bo'lishi mumkin.
      · `ip` — hamma uchun. U ATAYLAB BO'SH: O'zbekistonda mobil
        operatorlar CGNAT ishlatadi, ya'ni bir IP ortida minglab odam
        bo'lishi mumkin. Tor IP cheklovi butun mahallani bloklardi.
        Uning vazifasi — hisobsiz (anonim) suiiste'mol va bitta
        mashinadagi ko'p hisob.

    ⚠️ STAFF UCHUN ISTISNO YO'Q — ataylab. "Moderatorga cheklov
       qo'llanmaydi" degan yashirin qoida hisob buzib kirilganda
       aynan eng kuchli hisobni cheklovsiz qoldirardi. Moderator
       harakatlari (D2-T2) bu dekorator bilan o'ralmagan, ya'ni ular
       baribir tez ishlaydi.
    """

    def orovchi(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def orash(request: HttpRequest, *args, **kwargs):
            if request.method not in SANALADIGAN_USULLAR:
                return fn(request, *args, **kwargs)

            cheklovlar = cheklovlarni_olish(nom)

            doiralar: list[tuple[str, str, Cheklov]] = []
            if request.user.is_authenticated and "foydalanuvchi" in cheklovlar:
                doiralar.append(
                    ("foydalanuvchi", str(request.user.pk), cheklovlar["foydalanuvchi"])
                )
            if "ip" in cheklovlar:
                doiralar.append(("ip", mijoz_ip(request), cheklovlar["ip"]))

            for doira, belgi, cheklov in doiralar:
                try:
                    soni = _sanash(nom=nom, doira=doira, belgi=belgi, cheklov=cheklov)
                except Exception:
                    # Fail open (modul docstring'iga qarang).
                    log.exception("Tezlik cheklovi keshi ishlamadi: %s/%s", nom, doira)
                    return fn(request, *args, **kwargs)

                if soni > cheklov.soni:
                    qolgan = _oyna_oxirigacha(cheklov.oyna)
                    log.warning(
                        "Tezlik cheklovi: %s %s=%s (%s > %s), %ss qoldi",
                        nom,
                        doira,
                        belgi,
                        soni,
                        cheklov.soni,
                        qolgan,
                    )
                    return _429(request, cheklov=cheklov, qolgan=qolgan)

            return fn(request, *args, **kwargs)

        return orash

    return orovchi
