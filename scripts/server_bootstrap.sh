#!/usr/bin/env bash
# Dard.uz — yangi Ubuntu serverini deploy uchun tayyorlaydi.
#
# BIR MARTA ishlatiladi, root sifatida:
#     bash server_bootstrap.sh
#
# Idempotent: qayta ishlatilsa zarar qilmaydi.
#
# Nima qiladi:
#   1. Tizimni yangilaydi
#   2. `dard` foydalanuvchisini yaratadi (root'dan ishlamaymiz)
#   3. Docker + Compose plugin
#   4. Swap (kichik dropletda OOM'ning oldini oladi)
#   5. ufw: faqat 22/80/443
#   6. fail2ban: SSH'ga brute-force himoyasi
#   7. SSH: parol bilan kirishni O'CHIRADI
#   8. /opt/dard katalogi
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-dard}"
APP_DIR="/opt/dard"
SWAP_GB="${SWAP_GB:-2}"

log() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
xato() { printf "\n\033[1;31mXATO: %s\033[0m\n" "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || xato "root sifatida ishlating: sudo bash $0"

# ---------------------------------------------------------------------------
log "1/8  Tizim yangilanmoqda"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades

# Xavfsizlik yangilanishlari avtomatik o'rnatilsin.
# ⚠️ Yolg'iz ishlanayotgan loyihada serverni qo'lda yangilash UNUTILADI.
dpkg-reconfigure -f noninteractive unattended-upgrades

# ---------------------------------------------------------------------------
log "2/8  Deploy foydalanuvchisi: $DEPLOY_USER"
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi

# root'ning SSH kalitlarini ko'chiramiz — aks holda yangi foydalanuvchi
# bilan ulanib bo'lmaydi va parol kirishini o'chirgach serverdan
# BUTUNLAY chiqib qolish mumkin.
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then
    install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" \
        /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
else
    xato "/root/.ssh/authorized_keys topilmadi. Droplet yaratishda SSH kalit qo'shilganmi?"
fi

# ---------------------------------------------------------------------------
log "3/8  Docker"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$DEPLOY_USER"
systemctl enable --now docker

# Loglar diskni to'ldirmasin — bu kichik dropletda haqiqiy xavf
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
systemctl restart docker

# ---------------------------------------------------------------------------
log "4/8  Swap (${SWAP_GB}G)"
# ⚠️ 4GB dropletda Postgres + Redis + Gunicorn + 2 Celery jarayoni
#    xotira cho'qqisida OOM-killer'ga uchraydi. Swap sekin, lekin
#    jarayonning O'LDIRILISHIDAN yaxshiroq.
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l "${SWAP_GB}G" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Swap'ga faqat zarurat bo'lganda murojaat qilinsin
    sysctl -w vm.swappiness=10 >/dev/null
    grep -q 'vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

# ---------------------------------------------------------------------------
log "5/8  Xavfsizlik devori (ufw)"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'SSH' >/dev/null
ufw allow 80/tcp comment 'HTTP' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw --force enable >/dev/null

# ⚠️ PostgreSQL (5432) va Redis (6379) ATAYLAB OCHILMAGAN.
#    Ular faqat Docker ichki tarmog'ida ko'rinadi
#    (docker-compose.prod.yml da `ports: !override []`).
#    Kerak bo'lsa SSH tunnel: ssh -L 5432:localhost:5432 ...

# ---------------------------------------------------------------------------
log "6/8  fail2ban"
cat > /etc/fail2ban/jail.local <<'INI'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
findtime = 10m
INI
systemctl enable --now fail2ban
systemctl restart fail2ban

# ---------------------------------------------------------------------------
log "7/8  SSH qattiqlashtirish"
# ⚠️ Bu qadamdan OLDIN yangi foydalanuvchi bilan ulanib ko'ring!
#    Parol kirishi o'chirilgandan keyin kalit ishlamasa, serverga
#    faqat DigitalOcean konsoli orqali kirish mumkin bo'ladi.
cat > /etc/ssh/sshd_config.d/99-dard.conf <<'CONF'
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
CONF
sshd -t || xato "sshd konfiguratsiyasi noto'g'ri — qayta ishga tushirilmadi"
systemctl reload ssh || systemctl reload sshd

# ---------------------------------------------------------------------------
log "8/8  Ilova katalogi"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/backups"

cat <<EOF

╭──────────────────────────────────────────────────────────────╮
│  Server tayyor.                                              │
╰──────────────────────────────────────────────────────────────╯

  Foydalanuvchi : $DEPLOY_USER
  Katalog       : $APP_DIR
  Docker        : $(docker --version)
  Swap          : $(free -h | awk '/Swap/ {print $2}')
  Portlar       : 22, 80, 443 (db va redis TASHQARIDAN YOPIQ)

  KEYINGI QADAM — ulanishni HOZIR tekshiring (bu terminalni yopmang):

      ssh $DEPLOY_USER@<IP>

  Ishlasa davom eting. Ishlamasa — bu terminal orqali tuzating,
  aks holda serverga kirish yo'li yopiladi.

EOF
