#!/usr/bin/env bash
# Instalacja panelu VPN na serwerze z WireGuardem.
# Uruchom jako root z katalogu deploy/:  sudo bash install.sh
set -euo pipefail

DIR=/opt/vpnhost
SRC="$(cd "$(dirname "$0")" && pwd)"
IMAGE_DEFAULT="ghcr.io/dawidziniewicz/vpnhost:latest"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mBŁĄD:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Uruchom przez sudo: sudo bash $0"

# 1. Docker -----------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Instaluję Dockera (oficjalny skrypt get.docker.com)…"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "Brak 'docker compose'. Zainstaluj pakiet docker-compose-plugin."
systemctl enable --now docker >/dev/null 2>&1 || true

# 2. WireGuard ----------------------------------------------------------------
IFACE=wg0
[ -f "$DIR/.env" ] && IFACE=$(grep -E '^WG_INTERFACE=' "$DIR/.env" | cut -d= -f2 || echo wg0)
IFACE=${IFACE:-wg0}
[ -f "/etc/wireguard/$IFACE.conf" ] || die "Nie znaleziono /etc/wireguard/$IFACE.conf. Najpierw skonfiguruj WireGuarda."
if grep -qiE '^\s*SaveConfig\s*=\s*true' "/etc/wireguard/$IFACE.conf"; then
  warn "W /etc/wireguard/$IFACE.conf jest 'SaveConfig = true'. Wyłączam je, żeby wg-quick nie nadpisywał zmian z panelu."
  cp "/etc/wireguard/$IFACE.conf" "/etc/wireguard/$IFACE.conf.przed-panelem"
  sed -i -E 's/^\s*SaveConfig\s*=\s*true/# SaveConfig = true  (wyłączone przez panel VPN)/I' "/etc/wireguard/$IFACE.conf"
fi
cp -n "/etc/wireguard/$IFACE.conf" "/etc/wireguard/$IFACE.conf.kopia-$(date +%Y%m%d)" 2>/dev/null || true

# 3. Liczniki bajtów dla połączeń (zakładka „Połączenia”) ----------------------
echo "net.netfilter.nf_conntrack_acct=1" > /etc/sysctl.d/90-vpnhost.conf
sysctl -q -w net.netfilter.nf_conntrack_acct=1 || warn "Nie udało się włączyć nf_conntrack_acct"

# 4. Pliki panelu ---------------------------------------------------------------
say "Kopiuję pliki do $DIR"
mkdir -p "$DIR/data"
install -m 644 "$SRC/docker-compose.yml" "$DIR/docker-compose.yml"
install -m 755 "$SRC/updater.sh" "$DIR/updater.sh"
chmod 700 "$DIR/data"

if [ ! -f "$DIR/.env" ]; then
  say "Konfiguracja panelu"
  read -rp "Adres serwera dla klientów (np. twoja-nazwa.duckdns.org:51820): " ENDPOINT
  while :; do
    read -rsp "Hasło do panelu (min. 8 znaków): " PASS; echo
    read -rsp "Powtórz hasło: " PASS2; echo
    [ "$PASS" = "$PASS2" ] && [ ${#PASS} -ge 8 ] && [[ "$PASS" != *"'"* ]] && break
    warn "Hasła są różne, za krótkie albo zawierają apostrof ('). Spróbuj jeszcze raz."
  done
  LAN=$(ip -4 route show scope link | awk '!/wg|docker|br-/{print $1; exit}')
  umask 077
  cat > "$DIR/.env" <<EOF
ADMIN_USER=admin
ADMIN_PASSWORD='$PASS'
WG_ENDPOINT=$ENDPOINT
WG_DNS=1.1.1.1
LAN_SUBNET=${LAN:-192.168.1.0/24}
WG_INTERFACE=wg0
PANEL_PORT=8090
UPDATE_INTERVAL=60
PANEL_IMAGE=$IMAGE_DEFAULT
EOF
  umask 022
fi
chmod 600 "$DIR/.env"

# 5. Dostęp do obrazu w GitHub Container Registry ------------------------------
IMAGE=$(grep -E '^PANEL_IMAGE=' "$DIR/.env" | cut -d= -f2-)
IMAGE=${IMAGE:-$IMAGE_DEFAULT}
if ! docker pull -q "$IMAGE" >/dev/null 2>&1; then
  say "Obraz $IMAGE jest prywatny. Potrzebny jest token GitHub z uprawnieniem read:packages"
  echo "    (GitHub → Settings → Developer settings → Personal access tokens (classic) → zaznacz tylko read:packages)"
  read -rp "Login GitHub: " GH_USER
  read -rsp "Token: " GH_TOKEN; echo
  echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
  docker pull -q "$IMAGE" >/dev/null || die "Nadal nie mogę pobrać $IMAGE. Sprawdź token i czy GitHub Actions zbudował obraz."
fi
mkdir -p /root/.docker

# 6. Start ----------------------------------------------------------------------
say "Uruchamiam panel"
cd "$DIR"
docker compose up -d
sleep 3
PORT=$(grep -E '^PANEL_PORT=' "$DIR/.env" | cut -d= -f2)
IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
WGIP=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
say "Gotowe!"
echo "    Panel w sieci domowej:  http://${IP:-adres-serwera}:${PORT:-8090}"
[ -n "$WGIP" ] && echo "    Panel przez VPN:        http://$WGIP:${PORT:-8090}"
echo "    Login: admin (hasło takie, jak podałeś)"
echo "    Nowe wersje instalują się same po każdym pushu na gałąź main."
echo "    Logi: docker logs -f vpnhost-panel   |   docker logs -f vpnhost-updater"
