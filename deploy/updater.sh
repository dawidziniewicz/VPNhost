#!/bin/sh
# Automatyczna aktualizacja panelu: pobiera najnowszy obraz z GHCR
# i restartuje kontener tylko wtedy, gdy obraz się zmienił.
INTERVAL="${UPDATE_INTERVAL:-60}"
cd /opt/vpnhost || exit 1

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
log "updater: sprawdzam aktualizacje co ${INTERVAL}s"

while true; do
  image=$(docker compose config --images panel 2>/dev/null | head -n1)
  if [ -n "$image" ] && docker pull -q "$image" >/dev/null 2>/tmp/pull.err; then
    latest=$(docker image inspect -f '{{.Id}}' "$image" 2>/dev/null)
    running=$(docker inspect -f '{{.Image}}' vpnhost-panel 2>/dev/null)
    if [ -n "$latest" ] && [ "$latest" != "$running" ]; then
      log "nowa wersja $image (${latest#sha256:}): restartuję panel"
      if docker compose up -d --no-deps panel; then
        docker image prune -f >/dev/null 2>&1
        log "panel zaktualizowany"
      else
        log "BŁĄD: nie udało się uruchomić nowej wersji"
      fi
    fi
  else
    log "nie udało się pobrać obrazu: $(tr '\n' ' ' < /tmp/pull.err 2>/dev/null)"
  fi
  sleep "$INTERVAL"
done
