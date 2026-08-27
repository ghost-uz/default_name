"""Celery ilovasi.

Vazifalar rejaga ko'ra 3-bosqichda kerak bo'ladi (Telegram kanalga avto-post),
lekin M1 dayoq ishlatiladi: trending (`hot_score`) qayta hisoblash — D1-T11.

⚠️ Windows'da lokal ishga tushirilsa `--pool=solo` kerak (standart `prefork`
   Windows'da ishlamaydi). Docker ichida Linux — muammo yo'q.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("dard")

# Barcha Celery sozlamalari Django settings'da `CELERY_` prefiksi bilan
# turadi — sozlamalar bitta joyda bo'lsin.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Har ilovadagi tasks.py avtomatik topiladi
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self) -> str:
    """Celery ulanganini tekshirish uchun (D0-T3 qabul mezoni).

    ⚠️ `ignore_result=True` ATAYLAB QO'YILMAGAN. Natija saqlanmasa
    `.get()` hech narsa qaytarmaydi va vazifa bajarilgan-bajarilmaganini
    bilib bo'lmaydi — ya'ni tekshiruv vazifasi tekshirmaydigan bo'lib qoladi.
    Bu yerda bizga aynan NATIJA BACKEND'i ishlayotgani kerak.

    Haqiqiy vazifalarda esa aksincha: natija kerak bo'lmasa
    `ignore_result=True` qo'ying — aks holda Redis foydasiz natijalar bilan
    to'ladi.
    """
    return f"Celery ishlayapti: {self.request.id}"
