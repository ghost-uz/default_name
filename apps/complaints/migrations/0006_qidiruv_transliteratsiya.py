"""Transliteratsiya va apostrof qoidasi bo'yicha qayta indekslash (D4-T2).

⚠️⚠️ NEGA BU MIGRATSIYA KERAK — SXEMA UMUMAN O'ZGARMAYDI

   D4-T2 da `apps/common/matn.py::qidiruv_uchun()` o'zgardi: kiril ->
   lotin transliteratsiyasi qo'shildi va apostrof endi o'chiriladi.
   Ustunlar va indekslar esa AYNI holicha qoldi.

   Lekin `qidiruv_sarlavha` / `qidiruv_tavsif` — SAQLANGAN qiymat.
   Ya'ni bu kod chiqarilgandan keyin:

     · yangi va tahrirlangan postlar YANGI qoidalar bilan yoziladi;
     · eski postlar ESKI shaklda qolaveradi.

   Natijada qidiruv yarim ishlaydigan holatga tushardi va buni hech
   narsa bildirmasdi — na xato, na ogohlantirish. Faqat "eski postlar
   nega topilmayapti?" degan savol qolardi.

⚠️ NEGA QO'LDA BAJARILADIGAN QADAM EMAS
   `python manage.py qidiruvni_yangilash` buyrug'i bor va u aynan shu
   ishni qiladi. Lekin deploy'da qo'lda bajariladigan qadam — bir kuni
   albatta unutiladigan qadam. Migratsiya esa `docker entrypoint` da
   avtomatik ishlaydi va tartibi kafolatlangan.

   Buyruq baribir kerak: keyingi o'zgarishlar (yangi harf, yangi
   qoida) uchun va nosozlikni ta'mirlash uchun (DEPLOY.md 8-bo'lim).

⚠️ TESKARI YO'L YO'Q (`noop`): eski normal shaklni tiklash mumkin emas —
   u ma'lumot emas, hisoblangan qiymat. Orqaga qaytarilsa keyingi
   `qidiruvni_yangilash` uni baribir tiklaydi.
"""

from django.db import migrations

TOPLAM = 500


def _qayta_indekslash(apps, schema_editor):
    """Barcha yozuvlarni HOZIRGI normallashtirish qoidalari bilan yozadi.

    ⚠️ Tarixiy modelning menejeri filtrlamaydi — yumshoq o'chirilgan va
       yashirilgan yozuvlar ham qayta indekslanadi. Tiklangan post
       (D2-T2) qidiruvda darhol paydo bo'lishi kerak.
    """
    from apps.common.matn import qidiruv_uchun

    Complaint = apps.get_model("complaints", "Complaint")

    partiya = []
    for muammo in Complaint.objects.all().only("id", "title", "description").iterator():
        muammo.qidiruv_sarlavha = qidiruv_uchun(muammo.title)
        muammo.qidiruv_tavsif = qidiruv_uchun(muammo.description)
        partiya.append(muammo)
        if len(partiya) >= TOPLAM:
            Complaint.objects.bulk_update(
                partiya, ["qidiruv_sarlavha", "qidiruv_tavsif"]
            )
            partiya.clear()

    if partiya:
        Complaint.objects.bulk_update(partiya, ["qidiruv_sarlavha", "qidiruv_tavsif"])


class Migration(migrations.Migration):
    dependencies = [
        ("complaints", "0005_qidiruv_indeksi"),
    ]

    operations = [
        migrations.RunPython(_qayta_indekslash, migrations.RunPython.noop),
    ]
