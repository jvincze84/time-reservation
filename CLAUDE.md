# Időpontfoglaló – projektjegyzet

Mobilra optimalizált időpontfoglaló webapp Dockerben. A userrel **magyarul** kommunikálunk.
A felület **kétnyelvű (magyar + angol)**, az alapértelmezés a magyar. A konténer logja **angol**.
A felhasználói dokumentáció kétnyelvű: `README.md` (angol) és `README.hu.md` (magyar). Ha új funkció, env változó vagy működésbeli változás jön, **mindkettőt** frissíteni kell.

## Stack
- Python 3.13 + Flask, Gunicorn (1 worker, 8 szál, mert SQLite-ot használ), beépített `sqlite3`
- Szerveroldali Jinja sablonok, sima JS (nincs keretrendszer, nincs build lépés, nincs külső CDN)
- Minden backend-logika egyetlen fájlban: `app/app.py`

## Fájlok
- `app/app.py`: konfiguráció (env), séma és migráció, auth/CSRF, nézetek, admin, napló
- `app/i18n.py`: angol fordítások (`EN` szótár), nyelvfüggő dátum- és időtartam-formázás, `describe_rule`
- `app/templates/`:
  - `calendar.html`: a nap és a hét nézet (közös időrács)
  - `month.html`: a hónap nézet
  - `_calnav.html`, `_legend.html`: közös részek
  - `my.html`: Foglalásaim; az adminnak Saját/Mindenki váltóval és státusz-szűrővel
  - `admin.html`, `rules.html` (tiltások), `log.html` (napló), `login.html`, `error.html`
- `app/static/calendar.js`: kijelölés az időrácson (egérhúzás vagy Shift+kattintás; érintésen két koppintás vagy hosszú nyomás + húzás), alsó panelek (kijelölés, foglalás/tiltás részletei)
- `app/static/style.css`: mobile-first, sötét mód, 760px felett desktop elrendezés
- `config/users.json`: előre definiált userek (git-ignorált); minta: `users.example.json`
- `data/`: `reservation.db` és `.secret_key` (git-ignorált, csak a `.gitkeep` van a repóban)
- `tests/run.sh` + `tests/smoke_test.py`: füstteszt eldobható konténerben
- `tests/i18n_check.py`: hiányzó fordítások és `_()` nélküli sablonszövegek keresése
- `hashpw.py`: jelszó-hash generátor a users.json-hoz

## Adatmodell
- `users`: a `users.json`-ból szinkronizálódik induláskor; a fájlból kivett user `active=0` lesz
- `bookings`: `day`, `start`, `end` (HH:MM), `status`: pending/approved/rejected/cancelled. Az ütközést átfedés-ellenőrzés zárja ki (`BEGIN IMMEDIATE` + lock), nem egyedi index.
- `block_rules`: egységes tiltási szabály. Mezők: `weekdays` ("5,6", 0=hétfő), `date_from`/`date_to`, `time_from`/`time_to`. A NULL időmező egész napot jelent.
- `audit_log`: minden módosítás és belépés. A bejegyzést az `audit()` helper írja; a hívó commitolja a saját tranzakciójával együtt. A `details` **nyelvfüggetlen JSON** (pl. `{"day","start","end","owner"}`, `{"rule":{…},"reason"}`, `{"username"}`); a `log_details()` alakítja szöveggé az aktuális nyelven. A 2026-11-20 előtti bejegyzések kész magyar szövegek (legacy), ezek változatlanul jelennek meg.
- Sémaváltozás: a `SCHEMA`-ban `IF NOT EXISTS` / `DROP ... IF EXISTS` legyen. Induláskor fut, a meglévő éles DB-t nem törheti el.

## Szabályok és döntések
- A user mások foglalását csak „Foglalt”-ként látja (név nélkül), és nem módosíthatja; ezt szerveroldalon is ellenőrizni kell (403).
- Minden POST-hoz kell `_csrf` hidden input.
- Új módosító műveletnél mindig hívd az `audit()`-ot, és vedd fel a `LOG_ACTIONS`-ba.
- Az admin foglalása automatikusan jóváhagyott, és rá nem vonatkozik a min./max. foglalási hossz.
- Függő foglalásnál az admin csak Jóváhagy/Elutasít gombot lát, Lemondást nem (`can_cancel = ... and not can_decide`, a `build_days` és a `my_bookings` függvényben is). A szerver ettől még engedné a lemondást.
- „Lemondás” = a foglaló vagy az admin visszavonja (`cancelled`); „Elutasítás” = az admin nem engedélyezi (`rejected`). Értesítés (e-mail stb.) nincs.
- Konfiguráció csak env változókkal (lásd `docker-compose.yml` és a README-k).

## Többnyelvűség (i18n)
- A forrásnyelv a magyar: a magyar szöveg maga a kulcs. Pythonban `_("…")` (az aktuális kérés nyelvére fordít), sablonban `{{ _('…') }}`, modul szintű címkéknél `N_("…")` (csak jelölés, megjelenítéskor kell `_()`).
- Helyőrzők: `_("Legfeljebb {n} napra…", n=DAYS_AHEAD)`. Az angol fordításban ugyanazok a helyőrzők legyenek.
- **Minden új felhasználói szöveghez** vegyél fel angol fordítást az `app/i18n.py` `EN` szótárába, és futtasd: `python3 tests/i18n_check.py`.
- A JS szövegei a `js_i18n()`-ból jönnek (`window.I18N`, a `calendar.html` adja át); új JS szöveget oda vegyél fel, a JS-be ne írj be szöveget.
- Megerősítő kérdéshez `data-confirm="{{ _('…') }}"` attribútumot használj (a `base.html` kezeli), ne inline `onclick="confirm('…')"`-t.
- A nyelv a `lang` cookie-ban van (`/lang/<code>`), alapértelmezés: `DEFAULT_LANG` env (hu).
- A logolás (`log.info/warning/error`) mindig angol nyelvű.

## Futtatás
- Éles/fejlesztői példány: `docker compose up -d --build`, majd http://localhost:8090. A 8000-es és 8080-as port foglalt a gépen.
- Az éles példány DB-je lekérdezhető (csak olvasásra!): `docker compose exec -T reservation python -c "import sqlite3; ..."`.

## Tesztelés
- **Mindig a `./tests/run.sh`-t használd.** Először lefuttatja az `i18n_check.py`-t, utána külön konténert indít (8091-es port, `TEST_PORT`-tal állítható), ideiglenes üres `/data`-val és a `users.example.json` userekkel, majd eltakarít maga után. Az éles DB-hez nem nyúl.
- Új funkcióhoz bővítsd a `tests/smoke_test.py`-t (csak standard könyvtár; a `check()`-kel). A `run.sh` azt is ellenőrzi, hogy a konténer logjában nincs-e magyar szöveg.
- **Az éles példány (8090) ellen ne futtass módosító tesztet.** Múltkor egy teszt egy lista első elemét mondta le, ami a user valódi foglalása volt. Ha mégis kell valami az élesen, csak a saját, egyértelműen azonosított adatodhoz nyúlj, és utána takaríts el (a `created_at`/`ts` mező alapján).
- Böngésző nincs a gépen, és külső Docker image letöltését nem engedélyezi a jogosultságkezelés, ezért a JS/UI csak kézzel, kód-átnézéssel ellenőrizhető. Ezt mindig jelezd a usernek.

## Git
- A könyvtár git-repónak van előkészítve (`.gitignore`, `.gitattributes`), de a user maga inicializálja vagy kéri. **Commitolni és pusholni csak kérésre szabad.**
- Soha ne kerüljön a repóba: `config/users.json`, `data/*` (DB, `.secret_key`), `.env`. Commit előtt ellenőrizd a `git status`-t.

## Állapot (2026-11-20)
Kész, a user használja és teszteli: nap/hét/hónap nézet, változó hosszú foglalás húzással/koppintással, jóváhagyás, tiltási sorozatok, napló, Foglalásaim szűrővel (admin: Mindenki nézet), kétnyelvű felület (HU/EN).
Lehetséges következő lépések, amiket a user még nem kért: e-mail/push értesítés, szerveroldali tiltás az admin függő-lemondására, CSV export.
