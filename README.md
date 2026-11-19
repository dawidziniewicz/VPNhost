# VPNhost: panel WWW do serwera WireGuard

Panel do zarządzania serwerem WireGuard z przeglądarki. Działa w Dockerze na tym samym
serwerze co VPN i aktualizuje się sam po każdym pushu na gałąź `main`.

## Co potrafi

- **Klienci:** dodawanie, usuwanie, wyłączanie i włączanie, zmiana nazwy, nowe klucze.
  Do każdego klienta kod QR i plik `.conf` do pobrania.
- **Tryb ruchu dla klienta:** cały ruch przez dom albo tylko sieć domowa.
- **Pulpit:** stan WireGuarda, kto jest online, prędkość na żywo, wykres ruchu
  (na żywo, 1 godz., 24 godz., 7 dni, 30 dni).
- **Zasoby serwera:** procesor, RAM, dysk, temperatura, obciążenie, ruch na interfejsach.
- **Połączenia:** dokąd łączą się klienci VPN (adres, nazwa hosta, usługa, ilość danych)
  i najczęstsze cele.
- **Sieć domowa:** wszystkie urządzenia w sieci (IP, MAC, producent, nazwa, model), zgadywany typ
  (telefon, telewizor, drukarka, smart home…), własne nazwy i notatki, sprawdzanie otwartych portów,
  wpis w dzienniku, gdy pojawi się nowe urządzenie. Skan co 3 min (`LAN_SCAN_INTERVAL`).
- **Historia:** zużycie danych dziennie i według klientów, sesje (od kiedy, skąd, ile danych).
- **Dziennik:** połączenia, rozłączenia, zmiany adresu, zmiany klientów, logowania.
- **Ustawienia:** adres serwera (DuckDNS), DNS, sieć domowa, keepalive, MTU, zmiana hasła.

Panel zarządza istniejącym `/etc/wireguard/wg0.conf`. Sekcja `[Interface]` (z regułami NAT
w `PostUp`) zostaje nietknięta, a zmiany peerów są stosowane na żywo przez `wg syncconf`,
bez restartu VPN. Przed każdym zapisem robi kopię `wg0.conf.bak`.

## Jak działa aktualizacja

```
git push (main) ──► GitHub Actions: testy ► budowa obrazu ► ghcr.io/dawidziniewicz/vpnhost:latest
                                                                   │
serwer VPN: kontener vpnhost-updater co 60 s sprawdza obraz ◄──────┘
            i gdy jest nowy, podmienia kontener vpnhost-panel
```

Serwer sam pobiera nowe wersje, więc nie trzeba otwierać na routerze żadnych portów
dla GitHuba. Wersję widać w lewym dolnym rogu panelu.

## Instalacja na serwerze (jednorazowo)

1. Wypchnij repozytorium na GitHuba i poczekaj, aż w zakładce **Actions** zbuduje się obraz.
2. Ustaw obraz jako publiczny: GitHub → Twój profil → **Packages** → `vpnhost` →
   Package settings → Change visibility → **Public**. Obraz nie zawiera żadnych haseł ani kluczy.
   (Jeśli wolisz prywatny obraz, instalator poprosi o token GitHub z uprawnieniem `read:packages`.)
3. Skopiuj katalog `deploy/` na serwer i uruchom instalator:

   ```bash
   scp -r deploy vpn@192.168.1.76:~/vpnhost-deploy
   ssh -t vpn@192.168.1.76 'sudo bash ~/vpnhost-deploy/install.sh'
   ```

   Instalator zainstaluje Dockera (jeśli go nie ma), zapyta o adres serwera dla klientów
   (np. `twoja-nazwa.duckdns.org:51820`) i hasło do panelu, a potem uruchomi panel.
4. Otwórz **http://192.168.1.76:8090** w sieci domowej albo **http://10.8.0.1:8090** przez VPN.
   Login: `admin`.

Panelu **nie wystawiaj** na routerze do internetu. Jest dostępny w sieci domowej i przez VPN.

## Przydatne polecenia na serwerze

```bash
docker logs -f vpnhost-panel      # logi panelu
docker logs -f vpnhost-updater    # logi aktualizacji
cd /opt/vpnhost && sudo docker compose restart panel
```

Ustawienia startowe są w `/opt/vpnhost/.env`, a baza (klienci, historia) w `/opt/vpnhost/data`.

## Praca lokalna (tryb symulacji)

Bez WireGuarda, z udawanym ruchem:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
WG_MOCK=1 ADMIN_PASSWORD=demo12345 PANEL_HOST=127.0.0.1 .venv/bin/python -m app
# http://127.0.0.1:8090  (admin / demo12345)
.venv/bin/python -m pytest -q tests
```

## Struktura

| Ścieżka | Opis |
|---|---|
| `app/main.py` | API i strony panelu (FastAPI) |
| `app/service.py` | dodawanie, usuwanie i wyłączanie klientów, pliki konfiguracyjne |
| `app/wgconf.py` | odczyt i zapis `wg0.conf`, klucze |
| `app/wg.py` | `wg show dump` i `wg syncconf` (oraz symulacja) |
| `app/monitor.py` | pomiary co 2 s: prędkości, sesje, historia |
| `app/system.py`, `app/conntrack.py` | zasoby serwera, aktywne połączenia |
| `app/static/` | interfejs (HTML, CSS, JS bez zewnętrznych bibliotek) |
| `deploy/` | docker-compose, instalator, skrypt aktualizacji |
| `.github/workflows/build.yml` | testy i budowa obrazu (amd64 + arm64) |
