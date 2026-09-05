"""To'liq matnli qidiruv: normal matn ustunlari + tsvector + indekslar (D4-T1).

⚠️ TARTIB QO'LDA YOZILGAN, `makemigrations` NATIJASI EMAS.
   Avtodetektor `AddIndex(search_vector)` ni `AddField(search_vector)`
   dan OLDIN qo'ygan edi — ya'ni migratsiya hali mavjud bo'lmagan
   ustunga indeks qurmoqchi bo'lib yiqilardi. `GeneratedField` +
   `AddIndex` juftligida buni har safar tekshirish kerak.

⚠️ TARTIBNING IKKINCHI SABABI — TEJASH:
   normal matn ustunlari avval to'ldiriladi, `search_vector` esa
   SHUNDAN KEYIN qo'shiladi. Teskarisida PostgreSQL tsvector'ni ikki
   marta hisoblardi: bir marta bo'sh ustundan, ikkinchi marta
   to'ldirilgandan keyin.
"""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import migrations, models

TOPLAM = 500


def _toldirish(apps, schema_editor):
    """Mavjud yozuvlarni normal shaklga keltiradi.

    ⚠️ Yangi ustunlar standart `""` bilan qo'shiladi, ya'ni migratsiyadan
       keyin BUTUN eski kontent qidiruvda ko'rinmas bo'lardi — va buni
       hech narsa bildirmasdi (xato yo'q, natija bo'sh).

    ⚠️ `all_objects` mantiqi: yumshoq o'chirilgan va yashirilgan yozuvlar
       HAM to'ldiriladi. Tarixiy modelning menejeri filtrlamaydi va bu
       aynan kerakli xulq — tiklangan post qidiruvda paydo bo'lishi
       uchun qayta saqlashni talab qilmasin.

    ⚠️ Funksiya `apps.common.matn` dan import qilinadi. Migratsiyalarda
       ilova kodiga tayanish odatda tavsiya etilmaydi (u kelajakda
       o'zgaradi), lekin bu yerda u SOF FUNKSIYA va bir martalik
       to'ldirish uchun ishlatiladi. Qoidalar keyin o'zgarsa, qayta
       to'ldirish migratsiya emas — `manage.py qidiruvni_yangilash`.
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
        ("complaints", "0004_complaint_inqiroz_aniqlandi"),
        ("solutions", "0002_solution_inqiroz_aniqlandi"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ⚠️ DEPLOY'DA: `CREATE EXTENSION` SUPERUSER huquqini talab qiladi.
        #    O'z Postgres konteynerimizda `POSTGRES_USER` superuser, ya'ni
        #    dev va hozirgi prod'da muammo yo'q. Boshqariladigan bazaga
        #    (DigitalOcean, Neon, Supabase) ko'chilsa bu operatsiya ruxsat
        #    xatosi bilan yiqilishi mumkin — o'shanda kengaytmani panel
        #    orqali bir marta yoqib, bu operatsiyani `RunSQL` bilan
        #    `IF NOT EXISTS` shaklida almashtirish kerak bo'ladi.
        TrigramExtension(),
        migrations.AddField(
            model_name="complaint",
            name="qidiruv_sarlavha",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                verbose_name="qidiruv matni: sarlavha",
            ),
        ),
        migrations.AddField(
            model_name="complaint",
            name="qidiruv_tavsif",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                verbose_name="qidiruv matni: tavsif",
            ),
        ),
        migrations.RunPython(_toldirish, migrations.RunPython.noop),
        migrations.AddField(
            model_name="complaint",
            name="search_vector",
            field=models.GeneratedField(
                db_persist=True,
                expression=(
                    SearchVector("qidiruv_sarlavha", config="simple", weight="A")
                    + SearchVector("qidiruv_tavsif", config="simple", weight="B")
                ),
                output_field=SearchVectorField(),
                verbose_name="qidiruv vektori",
            ),
        ),
        migrations.AddIndex(
            model_name="complaint",
            index=GinIndex(fields=["search_vector"], name="complaint_qidiruv_gin"),
        ),
        migrations.AddIndex(
            model_name="complaint",
            index=GinIndex(
                fields=["qidiruv_sarlavha"],
                name="complaint_sarlavha_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
