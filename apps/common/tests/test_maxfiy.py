"""Maxfiy fayl ombori — guard testlari (D3-T5).

⚠️⚠️ NEGA ALOHIDA GUARD FAYLI

   Ekspert tasdiqlash hujjati — diplom, litsenziya yoki ish joyidan
   ma'lumotnoma. U sizib chiqishining UCHTA yo'li bor va uchalasi ham
   JIM sodir bo'ladi:

     1. Fayl `MEDIA_ROOT` ga tushadi -> nginx uni avtorizatsiyasiz
        uzatadi (`docker/nginx.conf` dagi `location /media/`).
     2. Shablonda `fayl.url` chizib qo'yiladi -> ochiq havola.
     3. Fayl git'ga tushadi -> repo OMMAVIY, tarixdan o'chirish
        deyarli imkonsiz.

   Uchalasi uchun ham bu yerda guard bor. Ular bir marta yozilib
   unutiladigan turdagi qoidalar — aynan shuning uchun test kerak.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages


def test_MAXFIY_ROOT_media_ichida_EMAS():
    """⭐⭐ Eng muhim invariant: maxfiy ildiz ommaviy media ichida emas."""
    maxfiy = Path(settings.MAXFIY_ROOT).resolve()
    media = Path(settings.MEDIA_ROOT).resolve()
    statik = Path(settings.STATIC_ROOT).resolve()

    assert not maxfiy.is_relative_to(media), (
        "MAXFIY_ROOT ommaviy media ichida — nginx uni avtorizatsiyasiz uzatardi."
    )
    assert not maxfiy.is_relative_to(statik)


def test_MAXFIY_ombor_URL_bermaydi():
    """⚠️ Oddiy `FileSystemStorage` `base_url` berilmasa `MEDIA_URL` ga
    QAYTADI (`_value_or_setting`) va `.url` ochiq ko'rinishdagi havola
    berardi. `MaxfiyStorage` uni ochiq rad etadi.

    Bu test aynan shu noto'g'ri taxminni fosh qilgan: dastlab sozlama
    "base_url yo'q, demak xato beradi" degan izoh bilan yozilgan edi va
    bu NOTO'G'RI edi.
    """
    ombor = storages["maxfiy"]

    with pytest.raises(ValueError, match="ommaviy havolasi"):
        ombor.url("ekspert/1/abc.pdf")


def test_MAXFIY_ombor_haqiqatan_MAXFIY_ILDIZGA_yozadi(tmp_path):
    ombor = storages["maxfiy"]
    nom = ombor.save("guard-sinov.txt", ContentFile(b"sinov"))
    try:
        yol = Path(ombor.path(nom)).resolve()
        assert yol.is_relative_to(Path(settings.MAXFIY_ROOT).resolve())
    finally:
        ombor.delete(nom)


def test_MAXFIY_katalog_GITIGNORE_da():
    """⭐⭐ Repo OMMAVIY. Bu qator bo'lmasa `git add -A` birovning
    diplomini GitHub'ga chiqarardi.

    ⚠️ `.gitignore` matnini o'qish yetarli emas — `git check-ignore`
       HAQIQIY qarorni beradi (naqsh noto'g'ri yozilgan bo'lishi
       mumkin: `maxfiy` va `/maxfiy/` bir xil ishlamaydi).
    """
    sinov = Path(settings.MAXFIY_ROOT) / "guard" / "sinov.pdf"
    sinov.parent.mkdir(parents=True, exist_ok=True)
    sinov.write_bytes(b"x")
    try:
        natija = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", str(sinov)],  # noqa: S607
            cwd=settings.BASE_DIR,
            capture_output=True,
            check=False,
        )
        assert natija.returncode == 0, (
            f"{sinov} git tomonidan KUZATILADI — .gitignore da `/maxfiy/` yo'qmi?"
        )
    finally:
        sinov.unlink(missing_ok=True)
