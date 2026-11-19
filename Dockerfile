FROM python:3.13-slim

ARG APP_VERSION=dev
ARG BUILD_DATE=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    BUILD_DATE=${BUILD_DATE}

# wireguard-tools: polecenie `wg` do odczytu stanu i `wg syncconf`
RUN apt-get update \
    && apt-get install -y --no-install-recommends wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baza producentów kart sieciowych (do rozpoznawania urządzeń w sieci domowej).
# Pobierana przy każdej budowie, więc jest aktualna. Bez niej panel działa, tylko nie pokazuje producenta.
RUN mkdir -p /usr/share/vpnhost && python -c "\
import urllib.request, sys; \
url = 'https://www.wireshark.org/download/automated/data/manuf'; \
req = urllib.request.Request(url, headers={'User-Agent': 'vpnhost-build'}); \
data = urllib.request.urlopen(req, timeout=60).read(); \
assert len(data) > 500000, 'za mały plik'; \
open('/usr/share/vpnhost/manuf', 'wb').write(data); \
print('manuf:', len(data), 'B')" || echo "UWAGA: nie udało się pobrać bazy producentów MAC"

COPY app ./app

EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PANEL_PORT\",\"8090\")}/api/health', timeout=4)"

CMD ["python", "-m", "app"]
