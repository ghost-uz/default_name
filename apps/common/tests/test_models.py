"""Abstrakt modellar (D0-T5) testlari.

⚠️ Abstrakt modelni to'g'ridan-to'g'ri sinab bo'lmaydi — unga jadval kerak.
   Shuning uchun quyida SINOV uchun konkret modellar e'lon qilinadi va
   ularning jadvallari `schema_editor` orqali qo'lda yaratiladi.
   Bu modellar migratsiyaga TUSHMAYDI: ular faqat test moduli import
   qilinganda ro'yxatga olinadi.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase
from django.utils import timezone

from apps.common.models import (
    ContentModel,
    ModeratedModel,
    ModerationStatus,
    SoftDeleteModel,
    TimeStampedModel,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Sinov modellari
# ---------------------------------------------------------------------------
class SinovVaqt(TimeStampedModel):
    nom = models.CharField(max_length=50)

    class Meta:
        app_label = "common"


class SinovOchirish(SoftDeleteModel):
    nom = models.CharField(max_length=50)

    class Meta:
        app_label = "common"


class SinovModeratsiya(ModeratedModel):
    nom = models.CharField(max_length=50)

    class Meta:
        app_label = "common"


class SinovKontent(ContentModel):
    nom = models.CharField(max_length=50)

    class Meta:
        app_label = "common"


SINOV_MODELLAR = [SinovVaqt, SinovOchirish, SinovModeratsiya, SinovKontent]


class SinovJadvalMixin:
    """Tarixiy nom — endi hech nima qilmaydi.

    ⚠️ ILGARI bu mixin jadvallarni `setUpClass` da yaratib, `tearDownClass`
       da O'CHIRARDI. Bu jim va topilishi qiyin xatoga olib keldi:

       Sinov modellari Django ilova reyestriga BUTUN SEANS uchun yoziladi
       (pytest test modulini yig'ish paytida import qiladi), jadvallari esa
       faqat shu sinf ichida mavjud bo'lardi. Boshqa istalgan testda
       `user.delete()` chaqirilsa, Django `SoftDeleteModel.deleted_by`
       teskari aloqasini ham yangilamoqchi bo'lib, mavjud bo'lmagan
       jadvalga urilardi. Test yolg'iz ishlaganda o'tardi, to'plamda
       yiqilardi — sabab esa butunlay boshqa faylda edi.

       Endi jadvallar `conftest.py` dagi seans darajasidagi fixture'da
       bir marta yaratiladi. Mixin merosxo'rlik zanjirini buzmaslik uchun
       qoldirildi.
    """


# ---------------------------------------------------------------------------
# 1. TimeStampedModel
# ---------------------------------------------------------------------------
class TimeStampedTests(SinovJadvalMixin, TestCase):
    def test_sanalar_avtomatik_qoyiladi(self):
        obj = SinovVaqt.objects.create(nom="a")
        self.assertIsNotNone(obj.created_at)
        self.assertIsNotNone(obj.updated_at)

    def test_created_at_ni_QOLDA_berish_mumkin(self):
        """⚠️ D7-T7 (sovuq start) uchun muhim.

        50-100 ta muammo qo'lda kiritilganda ular orqaga sanalangan
        bo'lishi kerak. `auto_now_add` berilgan qiymatni jim e'tiborsiz
        qoldirardi va hamma post bir daqiqada yaratilgandek ko'rinardi.
        """
        otgan = timezone.now() - timezone.timedelta(days=30)
        obj = SinovVaqt.objects.create(nom="eski", created_at=otgan)
        obj.refresh_from_db()
        self.assertEqual(obj.created_at, otgan)

    def test_updated_at_saqlashda_yangilanadi(self):
        obj = SinovVaqt.objects.create(nom="a")
        birinchi = obj.updated_at
        obj.nom = "b"
        obj.save()
        obj.refresh_from_db()
        self.assertGreater(obj.updated_at, birinchi)

    def test_created_at_tahrirlanmaydi(self):
        """editable=False -> formaga va admin tahririga tushmaydi."""
        maydon = SinovVaqt._meta.get_field("created_at")
        self.assertFalse(maydon.editable)


# ---------------------------------------------------------------------------
# 2. SoftDeleteModel
# ---------------------------------------------------------------------------
class SoftDeleteTests(SinovJadvalMixin, TestCase):
    def setUp(self):
        self.obj = SinovOchirish.objects.create(nom="post")

    def test_delete_bazadan_YOQ_QILMAYDI(self):
        self.obj.delete()
        self.assertTrue(SinovOchirish.all_objects.filter(pk=self.obj.pk).exists())

    def test_standart_menejer_ochirilganlarni_KORSATMAYDI(self):
        """Qabul mezoni #1."""
        self.obj.delete()
        self.assertEqual(SinovOchirish.objects.count(), 0)

    def test_all_objects_hammasini_qaytaradi(self):
        """Qabul mezoni #2."""
        self.obj.delete()
        self.assertEqual(SinovOchirish.all_objects.count(), 1)

    def test_deleted_at_belgilanadi(self):
        oldin = timezone.now()
        self.obj.delete()
        self.obj.refresh_from_db()
        self.assertIsNotNone(self.obj.deleted_at)
        self.assertGreaterEqual(self.obj.deleted_at, oldin)
        self.assertTrue(self.obj.is_deleted)

    def test_kim_ochirgani_yoziladi(self):
        """Audit uchun (D2-T7): nizo chiqsa kim o'chirgani kerak bo'ladi."""
        moderator = User.objects.create_user(username="moderatorx", password="x")
        self.obj.delete(user=moderator)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.deleted_by, moderator)

    def test_tiklash(self):
        self.obj.delete()
        self.obj.restore()
        self.assertEqual(SinovOchirish.objects.count(), 1)
        self.assertIsNone(self.obj.deleted_at)
        self.assertIsNone(self.obj.deleted_by)

    def test_hard_delete_haqiqatan_ochiradi(self):
        """Huquqiy talab / GDPR so'rovi uchun (D2-T8)."""
        pk = self.obj.pk
        self.obj.hard_delete()
        self.assertFalse(SinovOchirish.all_objects.filter(pk=pk).exists())

    def test_queryset_delete_ham_yumshoq(self):
        SinovOchirish.objects.create(nom="ikkinchi")
        SinovOchirish.objects.all().delete()
        self.assertEqual(SinovOchirish.objects.count(), 0)
        self.assertEqual(SinovOchirish.all_objects.count(), 2)

    def test_queryset_hard_delete(self):
        SinovOchirish.objects.all().hard_delete()
        self.assertEqual(SinovOchirish.all_objects.count(), 0)

    def test_alive_va_dead(self):
        tirik = SinovOchirish.objects.create(nom="tirik")
        self.obj.delete()
        self.assertEqual(list(SinovOchirish.all_objects.alive()), [tirik])
        self.assertEqual(
            [o.pk for o in SinovOchirish.all_objects.dead()], [self.obj.pk]
        )

    def test_ochirilgan_foydalanuvchi_deleted_by_ni_buzmaydi(self):
        """SET_NULL: moderator hisobi o'chsa yozuv qolaveradi."""
        moderator = User.objects.create_user(username="ketgan", password="x")
        self.obj.delete(user=moderator)
        # User `SoftDeleteModel` dan meros olmaydi -> haqiqiy o'chirish
        moderator.delete()
        self.obj.refresh_from_db()
        self.assertIsNone(self.obj.deleted_by)
        self.assertIsNotNone(self.obj.deleted_at)  # o'chirilgan holati saqlanadi


class SoftDeleteRelationTests(SinovJadvalMixin, TestCase):
    def test_oldinga_FK_ochirilgan_yozuvni_ham_topadi(self):
        """⚠️ `base_manager_name` belgilanmaganining sababi.

        Django filtrsiz `_base_manager` yasaydi, shuning uchun
        `solution.complaint` o'chirilgan ota-yozuvni ham qaytaradi.
        Aks holda tushunarsiz `RelatedObjectDoesNotExist` chiqardi.
        """
        moderator = User.objects.create_user(username="modx", password="x")
        obj = SinovOchirish.objects.create(nom="a")
        obj.delete(user=moderator)

        # deleted_by orqali FK bo'ylab yurish ishlashi kerak
        qayta = SinovOchirish.all_objects.get(pk=obj.pk)
        self.assertEqual(qayta.deleted_by.username, "modx")


# ---------------------------------------------------------------------------
# 3. ModeratedModel
# ---------------------------------------------------------------------------
class ModeratedTests(SinovJadvalMixin, TestCase):
    def test_standart_holat_VISIBLE(self):
        """Keyingi moderatsiya (post-moderation) — reja 13.1."""
        obj = SinovModeratsiya.objects.create(nom="a")
        self.assertEqual(obj.moderation_status, ModerationStatus.VISIBLE)
        self.assertTrue(obj.is_publicly_visible)

    def test_visible_faqat_korinadiganlarni_qaytaradi(self):
        korinadi = SinovModeratsiya.objects.create(nom="ok")
        for holat in (
            ModerationStatus.PENDING,
            ModerationStatus.HIDDEN,
            ModerationStatus.REMOVED,
        ):
            SinovModeratsiya.objects.create(nom=str(holat), moderation_status=holat)

        natija = list(SinovModeratsiya.objects.visible())
        self.assertEqual(natija, [korinadi])

    def test_moderatsiya_filtri_STANDART_EMAS(self):
        """⚠️ Soft delete'dan ataylab farq qiladi.

        Yashirilgan postni muallif ko'rishi KERAK — aks holda post
        "yo'qolgan" bo'lib ko'rinadi va ishonch yo'qoladi.
        """
        SinovModeratsiya.objects.create(
            nom="yashirin", moderation_status=ModerationStatus.HIDDEN
        )
        self.assertEqual(SinovModeratsiya.objects.count(), 1)  # ko'rinadi
        self.assertEqual(SinovModeratsiya.objects.visible().count(), 0)

    def test_under_review(self):
        SinovModeratsiya.objects.create(
            nom="tekshiruvda", moderation_status=ModerationStatus.PENDING
        )
        self.assertEqual(SinovModeratsiya.objects.under_review().count(), 1)


# ---------------------------------------------------------------------------
# 4. ContentModel — ikkalasi birga
# ---------------------------------------------------------------------------
class ContentModelTests(SinovJadvalMixin, TestCase):
    def test_ikkala_soro_metodi_ham_bor(self):
        SinovKontent.objects.create(nom="a")
        yashirin = SinovKontent.objects.create(
            nom="b", moderation_status=ModerationStatus.HIDDEN
        )
        ochirilgan = SinovKontent.objects.create(nom="c")
        ochirilgan.delete()

        # o'chirilgan avtomatik chiqib ketadi, yashirin esa visible() bilan
        self.assertEqual(SinovKontent.objects.count(), 2)
        self.assertEqual(SinovKontent.objects.visible().count(), 1)
        self.assertEqual(SinovKontent.all_objects.count(), 3)
        self.assertIn(yashirin, SinovKontent.objects.all())

    def test_zanjirlash_ishlaydi(self):
        """`objects.visible().alive()` kabi zanjir buzilmasin."""
        SinovKontent.objects.create(nom="a")
        natija = SinovKontent.all_objects.alive().visible()
        self.assertEqual(natija.count(), 1)

    def test_vaqt_belgilari_ham_meros_olinadi(self):
        obj = SinovKontent.objects.create(nom="a")
        self.assertIsNotNone(obj.created_at)
        self.assertIsNotNone(obj.updated_at)
