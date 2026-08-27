#!/bin/sh
# Dard.uz — konteyner kirish nuqtasi.
#
# set -e: istalgan buyruq yiqilsa konteyner ham yiqilsin. Migratsiya
# muvaffaqiyatsiz bo'lsa-yu server baribir ko'tarilsa — bu eng yomon holat:
# sayt ishlayotgandek ko'rinadi, lekin ma'lumotlar bazasi noto'g'ri holatda.
set -e

echo "==> PostgreSQL kutilmoqda (${POSTGRES_HOST}:${POSTGRES_PORT})..."
until python -c "
import os, socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.environ['POSTGRES_HOST'], int(os.environ['POSTGRES_PORT'])))
except OSError:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "==> PostgreSQL tayyor."

# ⚠️ Migratsiya FAQAT bir joyda ishlashi kerak. Celery worker/beat ham shu
#    entrypoint'ni ishlatadi — ular parallel migratsiya qilsa poyga holati
#    yuzaga keladi. RUN_MIGRATIONS faqat `web` xizmatida yoqiladi.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "==> Migratsiyalar..."
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
    echo "==> collectstatic..."
    python manage.py collectstatic --noinput --clear
fi

echo "==> Ishga tushmoqda: $*"
exec "$@"
