"""`ExpertProfile.pro_until` -> `payments.Subscription` (D6-T1).

⚠️⚠️ MA'LUMOT AVVAL KO'CHIRILADI, KEYIN MAYDON O'CHIRILADI.
   Tartib teskari bo'lsa mavjud PRO ekspertlar obunasini JIMGINA
   yo'qotardi va buni faqat ular sezardi ("nishonim qani?").

⚠️ `RunPython` ga TESKARI funksiya berilgan: `migrate accounts 0007`
   ishlashi kerak. Qaytarish yo'q migratsiya — ishlab chiqarishda
   rollback yo'lini yopadi.
"""

from django.db import migrations
from django.utils import timezone


def obunaga_kochirish(apps, schema_editor):
    ExpertProfile = apps.get_model("accounts", "ExpertProfile")
    Subscription = apps.get_model("payments", "Subscription")

    hozir = timezone.now()
    yangilar = []
    for profil in ExpertProfile.objects.filter(pro_until__isnull=False).select_related(
        "user"
    ):
        yangilar.append(
            Subscription(
                user_id=profil.user_id,
                plan="pro",
                # ⚠️ Holat SANADAN hisoblanadi, "faol" deb qo'yilmaydi:
                #    muddati o'tgan eski qatorlar ko'chirishdan keyin
                #    birdan faol bo'lib qolmasin.
                status="faol" if profil.pro_until > hozir else "tugagan",
                started_at=profil.created_at,
                expires_at=profil.pro_until,
                auto_renew=False,
                created_at=hozir,
                updated_at=hozir,
            )
        )

    # ⚠️ `ignore_conflicts` — `user` da OneToOne cheklovi bor va
    #    migratsiya qayta ishga tushirilsa yiqilmasin.
    Subscription.objects.bulk_create(yangilar, ignore_conflicts=True)


def obunadan_qaytarish(apps, schema_editor):
    """Teskari yo'l: obunani `pro_until` ga qaytaradi.

    ⚠️ Bu bosqichda `pro_until` ustuni HALI MAVJUD (`RemoveField` undan
       KEYIN turadi va teskari tartibda avval qaytariladi).
    """
    ExpertProfile = apps.get_model("accounts", "ExpertProfile")
    Subscription = apps.get_model("payments", "Subscription")

    muddat = dict(Subscription.objects.values_list("user_id", "expires_at"))
    if not muddat:
        return

    profillar = list(ExpertProfile.objects.filter(user_id__in=muddat))
    for profil in profillar:
        profil.pro_until = muddat[profil.user_id]
    ExpertProfile.objects.bulk_update(profillar, ["pro_until"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_telegram_bloklandi"),
        # ⚠️ Obuna jadvali BU MIGRATSIYADAN OLDIN mavjud bo'lishi shart.
        ("payments", "0001_obuna"),
    ]

    operations = [
        migrations.RunPython(obunaga_kochirish, obunadan_qaytarish),
        migrations.RemoveField(
            model_name="expertprofile",
            name="pro_until",
        ),
    ]
