"""Ekspert profili va tasdiqlash oqimi (D3-T5)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ExpertProfile, TasdiqHolati
from apps.accounts.services import (
    ekspert_arizasi_topshirish,
    ekspert_arizasini_rad_etish,
    ekspert_maqomini_bekor_qilish,
    ekspertni_tasdiqlash,
)
from apps.complaints.factories import CategoryFactory
from apps.moderation.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def hujjat_fayli(nom: str = "diplom.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nom, b"%PDF-1.4 soxta diplom", content_type="application/pdf"
    )


def ariza_yaratish(*, user, hujjatli: bool = True, **kw) -> ExpertProfile:
    profil = ExpertProfile.objects.create(
        user=user,
        specialty=kw.pop("specialty", None) or CategoryFactory(),
        experience_years=kw.pop("experience_years", 5),
        kasbiy_tavsif=kw.pop("kasbiy_tavsif", "10 yil mehnat huquqi bo'yicha advokat."),
        hujjat=hujjat_fayli() if hujjatli else None,
        **kw,
    )
    return profil


def topshirilgan(*, user) -> ExpertProfile:
    profil = ariza_yaratish(user=user)
    return ekspert_arizasi_topshirish(profil=profil)


# ===========================================================================
# ⭐⭐ QABUL MEZONI: tasdiqlanmagan ekspert PRO nishonini ololmaydi
# ===========================================================================
def test_QABUL_MEZONI_tasdiqlanmagan_PRO_nishonini_OLOLMAYDI(user):
    """⭐⭐ Task `nega`: "'Tasdiqlangan' nishoni tasdiqlash jarayonisiz
    yolg'on".

    PRO — IKKI shartning kesishmasi: tasdiqlangan MALAKA va amaldagi
    MUDDAT. Faqat muddatga qarasak, to'lov qilgan (yoki `pro_until` ni
    admin'da qo'lda qo'ygan) tasdiqlanmagan odam "Tasdiqlangan PRO"
    nishonini olardi — ya'ni pul bilan ishonch sotib olinardi.
    """
    profil = ariza_yaratish(user=user)
    profil.pro_until = timezone.now() + timedelta(days=30)
    profil.save(update_fields=["pro_until"])

    assert profil.verification_status != TasdiqHolati.TASDIQLANGAN
    assert profil.pro_faolmi is False, "tasdiqsiz PRO nishoni berildi"


def test_TASDIQLANGAN_va_MUDDATLI_bolsa_PRO_faol(staff, user):
    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)
    profil.pro_until = timezone.now() + timedelta(days=30)
    profil.save(update_fields=["pro_until"])

    assert profil.pro_faolmi is True


def test_TASDIQLANGAN_lekin_MUDDATI_otgan_PRO_emas(staff, user):
    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)
    profil.pro_until = timezone.now() - timedelta(days=1)
    profil.save(update_fields=["pro_until"])

    assert profil.pro_faolmi is False


def test_FOYDALANUVCHI_ozini_TASDIQLAY_OLMAYDI(user):
    """⚠️ `verification_status` va `pro_until` FORMADA YO'Q — bu task
    `nega` bo'limidagi muammoning eng to'g'ridan-to'g'ri ko'rinishi."""
    from apps.accounts.forms import EkspertArizaForm

    maydonlar = set(EkspertArizaForm().fields)

    assert "verification_status" not in maydonlar
    assert "pro_until" not in maydonlar
    assert "verified_by" not in maydonlar


def test_NISHON_TASDIQLANGAN_profildan_keladi(auth_client, staff, user):
    """Profil sahifasidagi nishon haqiqiy manbaga qaraydi.

    ⚠️ Tekshiruv ANIQ: "Ekspert" so'zi navigatsiyada ham bor
       ("Ekspertlar" havolasi), shuning uchun NISHON sinfi qidiriladi.
       Testning birinchi versiyasi shu sababli yiqilgan edi.
    """
    yol = reverse("profile", args=[user.username])
    nishon = 'class="badge-pro"'
    assert nishon not in auth_client.get(yol).content.decode()

    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    matn = auth_client.get(yol).content.decode()
    assert nishon in matn
    assert "Ekspert" in matn


# ===========================================================================
# ⭐ QABUL MEZONI: hujjat yuklash va staff ko'rigi bor
# ===========================================================================
def test_QABUL_MEZONI_HUJJATSIZ_topshirib_bolmaydi(user):
    """⭐ Hujjatsiz ariza staff uchun tekshirib bo'lmaydigan narsa: u
    faqat "ishonaman/ishonmayman" taxminini qoldirardi va tasdiq yana
    yolg'onga aylanardi."""
    profil = ariza_yaratish(user=user, hujjatli=False)

    with pytest.raises(ValidationError, match="hujjat"):
        ekspert_arizasi_topshirish(profil=profil)


def test_topshirish_KUTILMOQDA_holatiga_otkazadi(user):
    profil = ariza_yaratish(user=user)

    ekspert_arizasi_topshirish(profil=profil)

    profil.refresh_from_db()
    assert profil.verification_status == TasdiqHolati.KUTILMOQDA
    assert profil.topshirilgan_at is not None


def test_TASDIQLANGAN_profil_qayta_topshirilmaydi(staff, user):
    """⚠️ Aks holda tasdiq jimgina "ko'rib chiqilmoqda" holatiga
    tushardi va odam nishonini sababsiz yo'qotardi."""
    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    with pytest.raises(ValidationError, match="allaqachon"):
        ekspert_arizasi_topshirish(profil=profil)


# ===========================================================================
# ⭐⭐ Hujjat maxfiyligi
# ===========================================================================
def test_HUJJAT_MEDIA_ROOT_DAN_TASHQARIDA(user):
    """⭐⭐ `/media/` nginx tomonidan AVTORIZATSIYASIZ uzatiladi
    (`docker/nginx.conf`), DEBUG'da esa Django uni `static()` bilan
    ochadi. Hujjat u yerga tushsa — havolani bilgan har kim diplomni
    o'qiy olardi.
    """
    profil = ariza_yaratish(user=user)

    yol = Path(profil.hujjat.path).resolve()
    media = Path(settings.MEDIA_ROOT).resolve()

    assert not yol.is_relative_to(media), (
        f"Hujjat OMMAVIY media ichida: {yol}. `storage=maxfiy_saqlash` tushib qolganmi?"
    )
    assert yol.is_relative_to(Path(settings.MAXFIY_ROOT).resolve())


def test_HUJJAT_URL_i_YOQ_ataylab(user):
    """⚠️ Maxfiy ombor `base_url` siz sozlangan, ya'ni `fayl.url`
    `ValueError` beradi. Shablonda tasodifan ommaviy havola chizib
    qo'yish GUARD emas, IMKONSIZ."""
    profil = ariza_yaratish(user=user)

    with pytest.raises(ValueError):
        _ = profil.hujjat.url


def test_HUJJAT_nomi_TAXMIN_QILIB_BOLMAYDI(user):
    """⚠️ Asl nom saqlanmaydi (u odamning ismini o'z ichiga olishi
    mumkin), o'rniga tasodifiy nom."""
    profil = ariza_yaratish(user=user)

    assert "diplom" not in profil.hujjat.name
    assert profil.hujjat.name.endswith(".pdf")


def test_hujjat_KORINISHI_STAFF_ga_cheklangan(auth_client, anonymous_client, user):
    profil = topshirilgan(user=user)
    yol = reverse("ekspert_hujjati", args=[profil.pk])

    assert anonymous_client.get(yol).status_code == 404
    assert auth_client.get(yol).status_code == 404


def test_hujjat_KORINISHI_STAFF_ga_ochiq(staff_client, user):
    """⚠️ `javob.close()` SHART: `FileResponse` faylni ochiq qoldiradi va
    pytest uni `ResourceWarning` bilan xatoga aylantiradi. Bu testning
    birinchi versiyasida unutilgan edi va xato BOSHQA testda chiqqan —
    ochiq deskriptor yig'ilib turgani uchun."""
    profil = topshirilgan(user=user)

    javob = staff_client.get(reverse("ekspert_hujjati", args=[profil.pk]))
    try:
        assert javob.status_code == 200
        assert javob["Cache-Control"] == "no-store, private"
        assert b"soxta diplom" in b"".join(javob.streaming_content)
    finally:
        javob.close()


def test_OCHIRILGAN_hujjatga_murojaat_404(staff_client, staff, user):
    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    javob = staff_client.get(reverse("ekspert_hujjati", args=[profil.pk]))

    assert javob.status_code == 404


# ===========================================================================
# ⭐ Staff qarori
# ===========================================================================
def test_TASDIQLASH_bayroqni_va_maydonlarni_qoyadi(staff, user):
    profil = topshirilgan(user=user)

    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    profil.refresh_from_db()
    user.refresh_from_db()
    assert profil.verification_status == TasdiqHolati.TASDIQLANGAN
    assert profil.verified_by == staff
    assert profil.verified_at is not None
    assert user.is_expert is True


def test_QAROR_bilan_birga_HUJJAT_OCHIRILADI(staff, user):
    """⭐⭐ Foydalanuvchi qarori: saqlanmagan ma'lumot sizib chiqa
    olmaydi. Jurnalda "hujjat tekshirildi" qoladi, faylning o'zi yo'q."""
    profil = topshirilgan(user=user)
    fayl_yoli = Path(profil.hujjat.path)
    assert fayl_yoli.exists()

    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    profil.refresh_from_db()
    assert not profil.hujjat
    assert not fayl_yoli.exists(), "fayl diskda qoldi"


def test_RAD_ETISHDA_ham_hujjat_ochiriladi(staff, user):
    profil = topshirilgan(user=user)
    fayl_yoli = Path(profil.hujjat.path)

    ekspert_arizasini_rad_etish(
        moderator=staff, profil=profil, sabab="Hujjat o'qilmadi"
    )

    assert not fayl_yoli.exists()


def test_RAD_ETISH_SABABSIZ_bolmaydi(staff, user):
    """⚠️ Sababsiz rad etish odamni "nima noto'g'ri edi?" degan javobsiz
    savol bilan qoldiradi — D2-T11 dagi "sababsiz cheklov" xatosining
    aynan o'zi."""
    profil = topshirilgan(user=user)

    with pytest.raises(ValidationError, match=r"[Ss]abab"):
        ekspert_arizasini_rad_etish(moderator=staff, profil=profil, sabab="   ")


def test_RAD_SABABI_foydalanuvchiga_KORSATILADI(auth_client, staff, user):
    profil = topshirilgan(user=user)
    ekspert_arizasini_rad_etish(
        moderator=staff, profil=profil, sabab="Diplom nusxasi o'qilmayapti"
    )

    matn = auth_client.get(reverse("ekspert_ariza")).content.decode()

    assert "Diplom nusxasi o&#x27;qilmayapti" in matn or "o'qilmayapti" in matn


def test_RAD_ETILGAN_ariza_QAYTA_topshiriladi(staff, user):
    profil = topshirilgan(user=user)
    ekspert_arizasini_rad_etish(
        moderator=staff, profil=profil, sabab="Hujjat noto'g'ri"
    )

    profil.hujjat = hujjat_fayli("yangi.pdf")
    profil.save(update_fields=["hujjat"])
    ekspert_arizasi_topshirish(profil=profil)

    profil.refresh_from_db()
    assert profil.verification_status == TasdiqHolati.KUTILMOQDA
    assert profil.rad_sababi == "", "eski sabab qoldi — chalg'ituvchi"


def test_MAQOMNI_BEKOR_QILISH_bayroqni_tushiradi(staff, user):
    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    ekspert_maqomini_bekor_qilish(
        moderator=staff, profil=profil, sabab="Malaka yolg'on ekan"
    )

    user.refresh_from_db()
    assert user.is_expert is False


def test_ODDIY_foydalanuvchi_tasdiqlay_OLMAYDI(user, other_user):
    profil = topshirilgan(user=user)

    with pytest.raises(PermissionDenied):
        ekspertni_tasdiqlash(moderator=other_user, profil=profil)


def test_KUTILAYOTGAN_ariza_TAHRIRLANMAYDI(auth_client, user):
    """⚠️ Aks holda moderator ochgan matn bilan saqlangan matn boshqa
    bo'lardi va u boshqa narsani ko'rib turib qaror qabul qilardi."""
    profil = topshirilgan(user=user)
    assert profil.tahrirlash_mumkinmi is False

    javob = auth_client.post(reverse("ekspert_ariza"), {"experience_years": 99})

    assert javob.status_code == 403


# ===========================================================================
# Audit jurnali (D2-T7)
# ===========================================================================
def test_TASDIQLASH_JURNALGA_tushadi(staff, user):
    profil = topshirilgan(user=user)

    ekspertni_tasdiqlash(moderator=staff, profil=profil, izoh="Diplom tekshirildi")

    yozuv = AuditLog.objects.get(action=AuditAction.EKSPERT_TASDIQLANDI)
    assert yozuv.kim == staff.username
    assert yozuv.izoh == "Diplom tekshirildi"
    # ⚠️ Fayl o'chdi, lekin "hujjat tekshirildi" DALILI qoldi.
    assert yozuv.malumot["hujjat_tekshirildi"] is True


def test_RAD_ETISH_va_BEKOR_QILISH_JURNALGA_tushadi(staff, user, other_user):
    p1 = topshirilgan(user=user)
    ekspert_arizasini_rad_etish(moderator=staff, profil=p1, sabab="Yaroqsiz")

    p2 = topshirilgan(user=other_user)
    ekspertni_tasdiqlash(moderator=staff, profil=p2)
    ekspert_maqomini_bekor_qilish(moderator=staff, profil=p2, sabab="Yolg'on")

    assert AuditLog.objects.filter(action=AuditAction.EKSPERT_RAD_ETILDI).exists()
    assert AuditLog.objects.filter(action=AuditAction.EKSPERT_BEKOR_QILINDI).exists()


# ===========================================================================
# Cheklov bilan o'zaro ta'sir (D2-T11)
# ===========================================================================
def test_CHEKLANGAN_ekspert_NISHONINI_YOQOTMAYDI(staff, user):
    """⚠️⚠️ Foydalanuvchi qarori: tasdiq — MALAKA haqida ("bu odam
    haqiqatan yurist"), cheklov esa XULQ haqida. Cheklangan odam yoza
    olmaydi, lekin eski javoblari malakali bo'lib qolaveradi.

    Maqomni faqat MALAKA yolg'on bo'lsa bekor qilamiz — va bu alohida,
    ongli harakat (`ekspert_maqomini_bekor_qilish`).
    """
    from apps.moderation.services import foydalanuvchini_cheklash

    profil = topshirilgan(user=user)
    ekspertni_tasdiqlash(moderator=staff, profil=profil)

    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    user.refresh_from_db()
    profil.refresh_from_db()
    assert user.is_currently_banned is True
    assert user.is_expert is True, "cheklov nishonni o'chirdi"
    assert profil.tasdiqlanganmi is True


# ===========================================================================
# Navbat sahifasi
# ===========================================================================
def test_NAVBAT_staff_ga_cheklangan(auth_client, anonymous_client):
    yol = reverse("ekspert_navbati")

    assert anonymous_client.get(yol).status_code == 404
    assert auth_client.get(yol).status_code == 404


def test_NAVBATDA_faqat_KUTILAYOTGANLAR(staff_client, staff, user, other_user):
    topshirilgan(user=user)
    tasdiqlangan = topshirilgan(user=other_user)
    ekspertni_tasdiqlash(moderator=staff, profil=tasdiqlangan)

    matn = staff_client.get(reverse("ekspert_navbati")).content.decode()

    assert f"@{user.username}" in matn
    assert f"@{other_user.username}" not in matn


def test_NAVBATDAN_tasdiqlash_ISHLAYDI(staff_client, user):
    profil = topshirilgan(user=user)

    staff_client.post(
        reverse("ekspert_qarori", args=[profil.pk]),
        {"qaror": "tasdiqlash", "izoh": "Hujjat joyida"},
    )

    user.refresh_from_db()
    assert user.is_expert is True


def test_NAVBATDAN_SABABSIZ_rad_etish_XABAR_beradi(staff_client, user):
    profil = topshirilgan(user=user)

    staff_client.post(
        reverse("ekspert_qarori", args=[profil.pk]), {"qaror": "rad_etish", "izoh": ""}
    )

    profil.refresh_from_db()
    assert profil.verification_status == TasdiqHolati.KUTILMOQDA, (
        "sababsiz rad etish o'tib ketdi"
    )
