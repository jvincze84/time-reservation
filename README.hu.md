# Időpontfoglaló

🇬🇧 [English version](README.md)

Könnyűsúlyú, **mobilra optimalizált** időpontfoglaló webalkalmazás Dockerben.
Előre megadott felhasználók foglalhatnak időpontot, az admin jóváhagyja őket, és letilthat időszakokat.

**Technológia:** Python 3.13 + Flask + SQLite (beépített), Gunicorn. JavaScript-keretrendszer és build lépés nincs.

---

## Funkciók

### Mindenki
- **Nap, Hét és Hónap nézet**. Az utoljára használt nézetet megjegyzi.
- **Tetszőleges hosszúságú foglalás** egy időrácson (alapból 30 perces lépésközzel).
  - Asztali gépen: **egérrel húzva**, vagy kattintás, majd Shift+kattintás a végére.
  - Mobilon: **koppintás a kezdetre, majd a végére**, vagy **hosszan nyomva, majd húzva**. A sima ujjhúzás görget.
- Megjegyzés fűzhető a foglaláshoz. A saját foglalás lemondható (a naptárban a foglalásra koppintva, vagy a „Foglalásaim” oldalon).
- **Foglalásaim**: minden saját foglalás, két csoportban (közelgő, illetve korábbi és lezárt), státusz szerinti szűrővel.
- Mások foglalásából csak annyi látszik, hogy „Foglalt”. A nevük nem látszik, és a foglalásuk nem módosítható.
- Sötét mód (a rendszerbeállítást követi).
- **Kétnyelvű felület: magyar és angol.** A fejlécben (és a belépő oldalon) lévő HU/EN kapcsolóval lehet váltani, a választást a böngésző megjegyzi. Alapértelmezés: magyar (`DEFAULT_LANG`).

### Admin
- Függő foglalások **jóváhagyása vagy elutasítása**: egyenként, mindet egyszerre, vagy közvetlenül a naptárból.
- Bármely foglalás lemondása. Függő foglalásnál az admin a Jóváhagy/Elutasít gombokat látja, Lemondást nem.
- **Foglalásaim → Mindenki** nézet: az összes felhasználó összes foglalása, a foglalók nevével.
- **Tiltások**:
  - **sorozat**: a hét napjai (pl. minden szombat és vasárnap), opcionálisan dátumtartománnyal és napszakkal;
  - **időszak**: pl. szabadság dec. 20-tól jan. 5-ig;
  - **gyors tiltás** a naptárból: egy kijelölt időtartam vagy az egész nap.
- Figyelmeztetés, ha egy új tiltás már meglévő foglalást érint.
- Az admin saját foglalása automatikusan jóváhagyott.
- **Napló**: minden módosítás és belépés (ki, mikor, mit, melyik IP-ről), felhasználóra és műveletre szűrhetően.

---

## Telepítés

Előfeltétel: Docker, Docker Compose.

```bash
git clone <repo-url> reservation
cd reservation
cp config/users.example.json config/users.json
nano config/users.json            # felhasználók és jelszavak – lásd lent!
docker compose up -d --build
```

Megnyitás: **http://localhost:8090** (a port a `docker-compose.yml`-ben állítható).

> A konténer az **1000-es UID-dal** fut, ezért a `data/` mappának írhatónak kell lennie ennek a felhasználónak.
> Ha a géped felhasználója nem 1000-es UID-ú: `sudo chown 1000 data`.

## Felhasználók

Regisztráció nincs, a felhasználók a `config/users.json` fájlban vannak:

```json
[
  { "username": "admin", "password": "eros-jelszo", "name": "Adminisztrátor", "admin": true },
  { "username": "anna",  "password": "masik-jelszo", "name": "Kiss Anna" }
]
```

- Legalább egy `"admin": true` felhasználó kell.
- Módosítás után: `docker compose restart`. Induláskor a fájl szinkronizálódik az adatbázisba.
- Akit kiveszel a fájlból, az inaktív lesz (nem tud belépni), de a foglalásai megmaradnak.
- **Jelszó hash-elve is megadható** (ajánlott), így a fájlban nincs sima szöveges jelszó:
  ```bash
  docker compose run --rm reservation python hashpw.py
  ```
  A kimenetet (`scrypt:...`) írd a `password` mezőbe.
- A `config/users.json` nem kerül a git repóba (`.gitignore`), csak a `users.example.json` minta.

## Beállítások

A `docker-compose.yml` `environment` részében:

| Változó | Alapérték | Leírás |
|---|---|---|
| `APP_TITLE` | (nyelvfüggő) | Az alkalmazás neve (fejléc, böngészőfül). Üresen: „Időpontfoglaló” / „Booking” |
| `APP_TZ` | Europe/Budapest | Időzóna |
| `DEFAULT_LANG` | hu | Alapértelmezett nyelv: `hu` vagy `en`. A felhasználó a felületen átválthatja |
| `DAY_START` / `DAY_END` | 08:00 / 20:00 | A napi foglalható időszak |
| `GRID_MINUTES` | 30 | Az időrács lépésköze percben (ennyi percenként lehet kezdeni és befejezni egy foglalást) |
| `MIN_BOOKING_MINUTES` | = `GRID_MINUTES` | Legrövidebb foglalás (az adminra nem vonatkozik) |
| `MAX_BOOKING_MINUTES` | 0 | Leghosszabb foglalás, 0 = korlátlan (az adminra nem vonatkozik) |
| `BOOKING_DAYS_AHEAD` | 60 | Ennyi napra előre lehet foglalni |
| `REQUIRE_APPROVAL` | true | `false` esetén minden foglalás azonnal jóváhagyott |
| `MAX_ACTIVE_PER_USER` | 0 | Aktív foglalások max. száma felhasználónként (0 = korlátlan) |
| `LOG_RETENTION_DAYS` | 365 | A napló bejegyzései ennyi nap után törlődnek (0 = soha) |
| `PROXY_COUNT` | 0 | Reverse proxy mögött `1`, hogy a naplóban a valódi kliens IP-je látszódjon |
| `COOKIE_SECURE` | false | `true`, ha HTTPS mögött fut (ajánlott) |
| `SECRET_KEY` | (generált) | Session-kulcs. Ha nincs megadva, a `data/.secret_key` fájlba generálódik |

A módosítás után: `docker compose up -d`.

> Ha a `GRID_MINUTES` vagy a `DAY_START`/`DAY_END` értékét megváltoztatod, a meglévő foglalások
> a régi időpontjukon maradnak, és úgy is jelennek meg.

## Frissítés

```bash
git pull
docker compose up -d --build
```

Az adatbázis-séma szükséges változásai induláskor automatikusan lefutnak.

## Mentés és visszaállítás

Minden adat a `data/` mappában van: `reservation.db` (SQLite) és `.secret_key`.

**Mentés futás közben is** (konzisztens másolat):

```bash
docker compose exec reservation python -c \
  "import sqlite3; sqlite3.connect('/data/reservation.db').execute(\"VACUUM INTO '/data/backup.db'\")"
mv data/backup.db ~/mentes/reservation-$(date +%F).db
```

(A `VACUUM INTO` egyetlen, önálló fájlt készít. Ha a cél már létezik, hibát ad, ezért helyezd át a mentés után.)

**Visszaállítás:**

```bash
docker compose down
cp ~/mentes/reservation-2026-01-31.db data/reservation.db
rm -f data/reservation.db-wal data/reservation.db-shm
docker compose up -d
```

## Éles üzem

- Tegyél elé **HTTPS reverse proxyt** (Caddy, Traefik, nginx), és állítsd be a `COOKIE_SECURE: "true"` és a `PROXY_COUNT: "1"` értéket.
- Ha a port csak a proxy felé kell, kösd a localhostra: `"127.0.0.1:8090:8000"`.
- Caddy példa:
  ```
  foglalas.example.hu {
      reverse_proxy 127.0.0.1:8090
  }
  ```
- Cseréld le a minta jelszavakat, és lehetőleg hash-elve add meg őket.

## Többnyelvűség

- A forrásnyelv a magyar: a kódban és a sablonokban a magyar szöveg maga a kulcs (`{{ _('Foglalásaim') }}`).
- Az angol fordítások az `app/i18n.py` `EN` szótárában vannak. Ha egy kulcs hiányzik, a magyar szöveg jelenik meg.
- Új szöveg felvételekor az angol fordítást is add hozzá. A `python3 tests/i18n_check.py` jelzi, ha valami fordítatlan maradt.
- A napló bejegyzései nyelvfüggetlen formában tárolódnak, így mindkét nyelven helyesen jelennek meg.
  (A többnyelvűség bevezetése előtti bejegyzések magyarul maradnak.)
- A konténer logja (`docker compose logs`) angol nyelvű.

## Tesztelés

Végponttól végpontig tartó füstteszt: belépés, foglalás, ütközések, jogosultságok, jóváhagyás, tiltások, nézetek, napló, mindkét nyelv.
Előtte lefut a fordítás-ellenőrzés is. **Eldobható konténerben** fut, üres adatbázissal és a `users.example.json` felhasználóival, így az éles adatokat nem érinti:

```bash
./tests/run.sh                 # alapból a 8091-es porton
TEST_PORT=9000 ./tests/run.sh
```

## Projektstruktúra

```
app/
  app.py                 # minden backend-logika (konfig, séma, auth, nézetek, admin, napló)
  i18n.py                # többnyelvűség: angol fordítások, dátumformátumok
  templates/             # Jinja sablonok (calendar.html = nap+hét, month.html, my.html, admin…)
  static/
    calendar.js          # kijelölés az időrácson, alsó panelek
    style.css            # mobile-first stílusok, sötét mód
config/
  users.example.json     # minta – másold users.json-ra
data/                    # futásidejű adatok (git-ignorált): SQLite, session-kulcs
tests/
  run.sh                 # fordítás-ellenőrzés + füstteszt eldobható konténerben
  smoke_test.py          # a teszt (csak standard könyvtár)
  i18n_check.py          # hiányzó fordítások keresése
hashpw.py                # jelszó-hash generátor
Dockerfile, docker-compose.yml, requirements.txt
README.md, README.hu.md  # dokumentáció angolul / magyarul
CLAUDE.md                # fejlesztői jegyzet (Claude Code-hoz)
```
