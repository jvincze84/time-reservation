# Booking app

🇭🇺 [Magyar változat](README.hu.md)

A lightweight, **mobile-first** appointment booking web app running in Docker.
Predefined users book time slots, an admin approves them and can block periods.

**Tech:** Python 3.13 + Flask + SQLite (built-in), Gunicorn. No JavaScript framework, no build step.

---

## Features

### Everyone
- **Day, week and month view**. The last used view is remembered.
- **Bookings of any length** on a time grid (30-minute steps by default).
  - Desktop: **drag with the mouse**, or click the start and Shift+click the end.
  - Mobile: **tap the start, then the end**, or **long-press and drag**. A normal swipe scrolls.
- Optional note on a booking. You can cancel your own bookings (tap the booking in the calendar, or use the “My bookings” page).
- **My bookings**: all your bookings in two groups (upcoming / past and closed), with a status filter.
- Other people's bookings only show as “Booked”: no names, and they can't be changed.
- Dark mode (follows the system setting).
- **Bilingual UI: Hungarian and English.** Switch with the HU/EN toggle in the header (and on the sign-in page); the browser remembers the choice. Default: Hungarian (`DEFAULT_LANG`).

### Admin
- **Approve or reject** pending bookings: one by one, all at once, or straight from the calendar.
- Cancel any booking. For a pending booking the admin sees Approve/Reject instead of Cancel.
- **My bookings → Everyone** view: every booking of every user, with names.
- **Blocks**:
  - **recurring**: weekdays (e.g. every Saturday and Sunday), optionally limited to a date range and a time of day;
  - **period**: e.g. holiday from Dec 20 to Jan 5;
  - **quick block** from the calendar: a selected time range or the whole day.
- Warning when a new block affects existing bookings.
- The admin's own bookings are approved automatically.
- **Log**: every change and sign-in (who, when, what, from which IP), filterable by user and action.

---

## Installation

Requirements: Docker, Docker Compose.

```bash
git clone <repo-url> reservation
cd reservation
cp config/users.example.json config/users.json
nano config/users.json            # users and passwords – see below!
docker compose up -d --build
```

Open **http://localhost:8090** (the port can be changed in `docker-compose.yml`).

> The container runs as **UID 1000**, so the `data/` folder must be writable by that user.
> If your user's UID is not 1000: `sudo chown 1000 data`.

## Users

There's no sign-up. Users are defined in `config/users.json`:

```json
[
  { "username": "admin", "password": "strong-password", "name": "Administrator", "admin": true },
  { "username": "anna",  "password": "another-password", "name": "Anna Kiss" }
]
```

- At least one `"admin": true` user is required.
- After editing: `docker compose restart`. The file is synced into the database on startup.
- Users removed from the file become inactive (they can't sign in), but their bookings are kept.
- **Passwords can be given as hashes** (recommended), so the file contains no plain-text passwords:
  ```bash
  docker compose run --rm reservation python hashpw.py
  ```
  Put the output (`scrypt:...`) into the `password` field.
- `config/users.json` is not committed to git (`.gitignore`); only the `users.example.json` sample is.

## Configuration

In the `environment` section of `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `APP_TITLE` | (per language) | App name (header, browser tab). Empty: “Időpontfoglaló” / “Booking” |
| `APP_TZ` | Europe/Budapest | Time zone |
| `DEFAULT_LANG` | hu | Default language: `hu` or `en`. Users can switch in the UI |
| `DAY_START` / `DAY_END` | 08:00 / 20:00 | Daily bookable hours |
| `GRID_MINUTES` | 30 | Time grid step in minutes (bookings start and end on these steps) |
| `MIN_BOOKING_MINUTES` | = `GRID_MINUTES` | Shortest booking (doesn't apply to the admin) |
| `MAX_BOOKING_MINUTES` | 0 | Longest booking, 0 = unlimited (doesn't apply to the admin) |
| `BOOKING_DAYS_AHEAD` | 60 | How many days ahead users can book |
| `REQUIRE_APPROVAL` | true | With `false`, every booking is approved immediately |
| `MAX_ACTIVE_PER_USER` | 0 | Max. active bookings per user (0 = unlimited) |
| `LOG_RETENTION_DAYS` | 365 | Log entries are deleted after this many days (0 = never) |
| `PROXY_COUNT` | 0 | Set to `1` behind a reverse proxy so the log shows the real client IP |
| `COOKIE_SECURE` | false | `true` when served over HTTPS (recommended) |
| `SECRET_KEY` | (generated) | Session key. If not set, it's generated into `data/.secret_key` |

Apply changes with `docker compose up -d`.

> If you change `GRID_MINUTES` or `DAY_START`/`DAY_END`, existing bookings keep their original
> times and are shown that way.

## Updating

```bash
git pull
docker compose up -d --build
```

Required database schema changes run automatically on startup.

## Backup and restore

All data lives in the `data/` folder: `reservation.db` (SQLite) and `.secret_key`.

**Backup, even while running** (consistent copy):

```bash
docker compose exec reservation python -c \
  "import sqlite3; sqlite3.connect('/data/reservation.db').execute(\"VACUUM INTO '/data/backup.db'\")"
mv data/backup.db ~/backups/reservation-$(date +%F).db
```

(`VACUUM INTO` creates a single self-contained file. It fails if the target exists, so move it away after the backup.)

**Restore:**

```bash
docker compose down
cp ~/backups/reservation-2026-01-31.db data/reservation.db
rm -f data/reservation.db-wal data/reservation.db-shm
docker compose up -d
```

## Production

- Put an **HTTPS reverse proxy** in front (Caddy, Traefik, nginx), and set `COOKIE_SECURE: "true"` and `PROXY_COUNT: "1"`.
- If the port only needs to be reachable by the proxy, bind it to localhost: `"127.0.0.1:8090:8000"`.
- Caddy example:
  ```
  booking.example.com {
      reverse_proxy 127.0.0.1:8090
  }
  ```
- Replace the sample passwords, preferably with hashes.

## Languages

- The source language is Hungarian: in the code and templates the Hungarian text itself is the key (`{{ _('Foglalásaim') }}`).
- English translations live in the `EN` dictionary in `app/i18n.py`. If a key is missing, the Hungarian text is shown.
- When adding new text, add the English translation too. `python3 tests/i18n_check.py` reports anything left untranslated.
- Log entries are stored in a language-neutral form, so they display correctly in both languages.
  (Entries created before multi-language support remain in Hungarian.)
- The container log (`docker compose logs`) is in English.

## Testing

End-to-end smoke test: sign-in, booking, overlaps, permissions, approval, blocks, views, log, both languages.
The translation check runs first. The test runs in a **throwaway container** with an empty database and the users from `users.example.json`, so production data is never touched:

```bash
./tests/run.sh                 # port 8091 by default
TEST_PORT=9000 ./tests/run.sh
```

## Project structure

```
app/
  app.py                 # all backend logic (config, schema, auth, views, admin, log)
  i18n.py                # languages: English translations, date formats
  templates/             # Jinja templates (calendar.html = day+week, month.html, my.html, admin…)
  static/
    calendar.js          # time grid selection, bottom sheets
    style.css            # mobile-first styles, dark mode
config/
  users.example.json     # sample – copy to users.json
data/                    # runtime data (git-ignored): SQLite, session key
tests/
  run.sh                 # translation check + smoke test in a throwaway container
  smoke_test.py          # the test (standard library only)
  i18n_check.py          # finds missing translations
hashpw.py                # password hash generator
Dockerfile, docker-compose.yml, requirements.txt
README.md, README.hu.md  # documentation in English / Hungarian
CLAUDE.md                # developer notes (for Claude Code)
```
