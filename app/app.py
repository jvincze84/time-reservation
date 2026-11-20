"""Időpontfoglaló alkalmazás – Flask + SQLite."""
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import i18n
from i18n import LANGS, N_

# A konténer logja angol nyelvű (a Gunicorn formátumához igazítva)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S %z")
log = logging.getLogger("reservation")

# --------------------------------------------------------------------------
# Konfiguráció (környezeti változókból)
# --------------------------------------------------------------------------
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "reservation.db")
USERS_FILE = os.environ.get("USERS_FILE", "/config/users.json")
TZ = ZoneInfo(os.environ.get("APP_TZ", "Europe/Budapest"))
DAY_START = os.environ.get("DAY_START", "08:00")
DAY_END = os.environ.get("DAY_END", "20:00")
# Az időrács felbontása (perc) – ennyi percenként lehet kezdeni/befejezni egy foglalást
GRID = int(os.environ.get("GRID_MINUTES") or os.environ.get("SLOT_MINUTES") or "30")
MIN_BOOKING = int(os.environ.get("MIN_BOOKING_MINUTES") or GRID)
MAX_BOOKING = int(os.environ.get("MAX_BOOKING_MINUTES") or "0")  # 0 = korlátlan
DAYS_AHEAD = int(os.environ.get("BOOKING_DAYS_AHEAD", "60"))
REQUIRE_APPROVAL = os.environ.get("REQUIRE_APPROVAL", "true").lower() in ("1", "true", "yes")
MAX_ACTIVE_PER_USER = int(os.environ.get("MAX_ACTIVE_PER_USER", "0"))  # 0 = korlátlan
APP_TITLE = os.environ.get("APP_TITLE", "").strip()  # üresen: nyelvfüggő alapértelmezett cím
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "365"))  # 0 = örökre
PROXY_COUNT = int(os.environ.get("PROXY_COUNT", "0"))  # reverse proxy-k száma (valós IP-hez)
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", i18n.DEFAULT_LANG)
if DEFAULT_LANG not in LANGS:
    DEFAULT_LANG = i18n.DEFAULT_LANG
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

# A címkék magyarul vannak megadva, megjelenítéskor a _() fordítja őket
STATUS_LABELS = {"pending": N_("Jóváhagyásra vár"), "approved": N_("Jóváhagyva"),
                 "rejected": N_("Elutasítva"), "cancelled": N_("Lemondva")}
ACTIVE = ("pending", "approved")
LOG_ACTIONS = {
    "login": N_("Belépés"), "login_failed": N_("Sikertelen belépés"),
    "book": N_("Foglalás"), "cancel": N_("Lemondás / törlés"),
    "approve": N_("Jóváhagyás"), "reject": N_("Elutasítás"),
    "rule_add": N_("Tiltás létrehozva"), "rule_delete": N_("Tiltás törölve"),
}
LOG_PAGE_SIZE = 50
# Foglalásaim oldal szűrői: kulcs -> (felirat, státuszok)
MY_FILTERS = {
    "active": (N_("Aktív"), ("pending", "approved")),
    "pending": (N_("Jóváhagyásra vár"), ("pending",)),
    "approved": (N_("Jóváhagyva"), ("approved",)),
    "closed": (N_("Lemondva / elutasítva"), ("cancelled", "rejected")),
}
MY_PAGE_SIZE = 50
VIEWS = ("day", "week", "month")


def _secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(DATA_DIR, ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    os.chmod(path, 0o600)
    return key


app = Flask(__name__)
if PROXY_COUNT:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=PROXY_COUNT, x_proto=PROXY_COUNT)
os.makedirs(DATA_DIR, exist_ok=True)
app.config.update(
    SECRET_KEY=_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
_write_lock = threading.Lock()

# --------------------------------------------------------------------------
# Adatbázis
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,            -- YYYY-MM-DD
    start TEXT NOT NULL,          -- HH:MM
    end TEXT NOT NULL,            -- HH:MM
    status TEXT NOT NULL,         -- pending|approved|rejected|cancelled
    note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
-- Régi verzió: fix idősávonként egyedi index – változó hosszúságú foglalásoknál már nem kell
DROP INDEX IF EXISTS ux_booking_active;
CREATE INDEX IF NOT EXISTS ix_booking_day ON bookings(day, status);
CREATE INDEX IF NOT EXISTS ix_booking_user ON bookings(user_id);
CREATE TABLE IF NOT EXISTS block_rules (
    id INTEGER PRIMARY KEY,
    date_from TEXT,               -- NULL = nincs alsó határ
    date_to TEXT,                 -- NULL = nincs felső határ
    weekdays TEXT,                -- pl. "5,6" (0=hétfő); NULL = minden nap
    time_from TEXT,               -- NULL = egész nap
    time_to TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    user_id INTEGER,              -- a műveletet végző felhasználó
    username TEXT,                -- megjelenítendő név (akkor is, ha a user később törlődik)
    action TEXT NOT NULL,
    details TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS ix_log_ts ON audit_log(ts);
"""


def db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now_local():
    return datetime.now(TZ).replace(tzinfo=None)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    sync_users(conn)
    if LOG_RETENTION_DAYS:
        cutoff = (now_local() - timedelta(days=LOG_RETENTION_DAYS)).isoformat(timespec="seconds")
        pruned = conn.execute("DELETE FROM audit_log WHERE ts < ?", (cutoff,)).rowcount
        if pruned:
            log.info("Pruned %d audit log entries older than %d days", pruned, LOG_RETENTION_DAYS)
    conn.commit()
    conn.close()
    log.info("Database ready: %s", DB_PATH)
    log.info("Config: hours %s-%s, grid %d min, booking length min %d / max %s min, approval %s, "
             "%d days ahead, timezone %s, default language %s",
             DAY_START, DAY_END, GRID, MIN_BOOKING, MAX_BOOKING or "unlimited",
             "required" if REQUIRE_APPROVAL else "not required", DAYS_AHEAD, TZ.key, DEFAULT_LANG)


def _fatal(msg):
    log.error(msg)
    raise SystemExit(msg)


def sync_users(conn):
    """A users.json tartalmát szinkronizálja az adatbázisba.

    Formátum: [{"username": "admin", "password": "...", "name": "Admin", "admin": true}, ...]
    A jelszó lehet sima szöveg vagy kész hash (scrypt:/pbkdf2: előtaggal).
    A fájlból eltávolított felhasználók inaktívvá válnak (foglalásaik megmaradnak).
    """
    if not os.path.exists(USERS_FILE):
        _fatal(f"Users file not found: {USERS_FILE} (copy config/users.example.json to config/users.json)")
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            users = json.load(f)
    except json.JSONDecodeError as e:
        _fatal(f"Invalid JSON in {USERS_FILE}: {e}")
    if not any(u.get("admin") for u in users):
        _fatal(f"{USERS_FILE} must contain at least one admin user (\"admin\": true)")
    seen = []
    for u in users:
        username = u["username"].strip().lower()
        pw = u["password"]
        pw_hash = pw if pw.startswith(("scrypt:", "pbkdf2:")) else generate_password_hash(pw)
        name = u.get("name") or u["username"]
        is_admin = 1 if u.get("admin") else 0
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?",
                           (username,)).fetchone()
        if row:
            if pw.startswith(("scrypt:", "pbkdf2:")) or not check_password_hash(row[1], pw):
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, row[0]))
            conn.execute("UPDATE users SET display_name = ?, is_admin = ?, active = 1 WHERE id = ?",
                         (name, is_admin, row[0]))
        else:
            conn.execute("INSERT INTO users (username, display_name, password_hash, is_admin) "
                         "VALUES (?, ?, ?, ?)", (username, name, pw_hash, is_admin))
        seen.append(username)
    placeholders = ",".join("?" * len(seen))
    deactivated = conn.execute(f"UPDATE users SET active = 0 WHERE active = 1 AND username NOT IN "
                               f"({placeholders})", seen).rowcount
    log.info("Users synced from %s: %d active (%d admin), %d deactivated", USERS_FILE, len(seen),
             sum(1 for u in users if u.get("admin")), deactivated)


# --------------------------------------------------------------------------
# Segédfüggvények: idő, rács, tiltások
# --------------------------------------------------------------------------
def _to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _dt(d, hhmm):
    return datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time())


DS, DE = _to_min(DAY_START), _to_min(DAY_END)


def grid_cells():
    out, t = [], DS
    while t + GRID <= DE:
        out.append((_to_hhmm(t), _to_hhmm(t + GRID)))
        t += GRID
    return out


GRID_STARTS = {s for s, _ in grid_cells()}
GRID_ENDS = {e for _, e in grid_cells()}


def lang():
    return g.get("lang", DEFAULT_LANG)


def _(text, **kw):
    """Fordítás az aktuális kérés nyelvére."""
    return i18n.translate(text, lang(), **kw)


def fmt_duration(minutes):
    return i18n.fmt_duration(minutes, lang())


def fmt_date(d):
    return i18n.fmt_date(d, lang())


def fmt_date_long(d):
    return i18n.fmt_date_long(d, lang())


def describe_rule(r):
    return i18n.describe_rule(r, lang())


def rules_for_day(d):
    ds = d.isoformat()
    rows = db().execute(
        "SELECT * FROM block_rules WHERE (date_from IS NULL OR date_from <= ?) "
        "AND (date_to IS NULL OR date_to >= ?)", (ds, ds)).fetchall()
    wd = str(d.weekday())
    return [r for r in rows if not r["weekdays"] or wd in r["weekdays"].split(",")]


def slot_block(rules, start, end):
    """Visszaadja az első olyan szabályt, ami a [start, end) időtartamot érinti (vagy None)."""
    for r in rules:
        if not r["time_from"]:
            return r
        if r["time_from"] < end and r["time_to"] > start:
            return r
    return None


def parse_day(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        abort(404)


def audit(action, details=None, user=None):
    """Naplóbejegyzés – a hívó commitolja a saját tranzakciójával együtt.

    A részletek nyelvfüggetlen JSON-ként tárolódnak; megjelenítéskor a log_details() fordítja.
    """
    u = user or g.get("user")
    db().execute(
        "INSERT INTO audit_log (ts, user_id, username, action, details, ip) VALUES (?, ?, ?, ?, ?, ?)",
        (now_local().isoformat(timespec="seconds"), u["id"] if u else None,
         u["display_name"] if u else None, action,
         json.dumps(details, ensure_ascii=False) if details else None, request.remote_addr))


def booking_details(b, owner=None, **extra):
    """A napló egy foglalásra vonatkozó részletei."""
    out = {"day": b["day"], "start": b["start"], "end": b["end"]}
    if owner:
        out["owner"] = owner
    out.update({k: v for k, v in extra.items() if v})
    return out


def rule_details(r, reason=None):
    return {"rule": {k: r[k] for k in ("date_from", "date_to", "weekdays", "time_from", "time_to")},
            "reason": reason}


def log_details(action, raw):
    """Naplóbejegyzés részleteinek szövege az aktuális nyelven.
    A JSON előtti (régi) bejegyzések kész magyar szövegként vannak tárolva – ezek változatlanul jelennek meg."""
    if not raw:
        return ""
    if not raw.startswith("{"):
        return raw
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if "day" in d:
        txt = f"{i18n.fmt_date_wd(date.fromisoformat(d['day']), lang())}, {d['start']}–{d['end']}"
        if d.get("owner"):
            txt = f"{d['owner']}: {txt}"
        if d.get("auto"):
            txt += f" ({_('azonnal jóváhagyva')})"
        if d.get("bulk"):
            txt += f" ({_('tömeges jóváhagyás')})"
        if d.get("note"):
            txt += f" – {i18n.quote(d['note'], lang())}"
        return txt
    if "rule" in d:
        return describe_rule(d["rule"]) + (f" – {d['reason']}" if d.get("reason") else "")
    if "username" in d:
        return _("Felhasználónév: {u}", u=d["username"])
    return raw


def _booking_with_owner(bid):
    return db().execute("SELECT b.*, u.display_name FROM bookings b JOIN users u ON u.id = b.user_id "
                        "WHERE b.id = ?", (bid,)).fetchone()


def build_days(dates):
    """Naponként összeállítja a rács-cellákat, a foglalásokat és a tiltásokat a megjelenítéshez."""
    now = now_local()
    today = now.date()
    uid, is_admin = g.user["id"], bool(g.user["is_admin"])
    rows = db().execute(
        "SELECT b.*, u.display_name FROM bookings b JOIN users u ON u.id = b.user_id "
        "WHERE b.day BETWEEN ? AND ? AND b.status IN ('pending','approved') ORDER BY b.start",
        (dates[0].isoformat(), dates[-1].isoformat())).fetchall()
    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)

    out = []
    for d in dates:
        rules = rules_for_day(d)
        bks = by_day.get(d.isoformat(), [])
        cells = []
        for s, e in grid_cells():
            if any(b["start"] < e and b["end"] > s for b in bks):
                st = "taken"
            elif slot_block(rules, s, e):
                st = "blocked"
            elif _dt(d, s) <= now:
                st = "past"
            elif d > today + timedelta(days=DAYS_AHEAD):
                st = "toofar"
            else:
                st = "free"
            cells.append(dict(start=s, end=e, state=st, hour=_to_min(s) % 60 == 0))

        bookings = []
        for b in bks:
            mine = b["user_id"] == uid
            s, e = max(_to_min(b["start"]), DS), min(_to_min(b["end"]), DE)
            if e <= s:
                continue
            # Függő foglalásnál az admin jóváhagy/elutasít – ott nem kínálunk „Lemondás”-t
            can_decide = is_admin and b["status"] == "pending"
            bookings.append(dict(
                id=b["id"], start=b["start"], end=b["end"], status=b["status"], mine=mine,
                label=_("Saját") if mine else (b["display_name"] if is_admin else _("Foglalt")),
                note=b["note"] if (mine or is_admin) else None,
                top=(s - DS) / GRID, height=(e - s) / GRID,
                can_cancel=(mine or is_admin) and _dt(d, b["start"]) > now and not can_decide,
                can_decide=can_decide))

        blocks = []
        for r in rules:
            s = max(_to_min(r["time_from"]) if r["time_from"] else DS, DS)
            e = min(_to_min(r["time_to"]) if r["time_to"] else DE, DE)
            if e <= s:
                continue
            blocks.append(dict(
                id=r["id"], reason=r["reason"], text=describe_rule(r), whole=not r["time_from"],
                series=bool(r["weekdays"]) or r["date_from"] != r["date_to"],
                top=(s - DS) / GRID, height=(e - s) / GRID))

        out.append(dict(
            date=d, cells=cells, bookings=bookings, blocks=blocks,
            free=sum(c["state"] == "free" for c in cells), total=len(cells),
            full_block=any(x["whole"] for x in blocks),
            pending=sum(b["status"] == "pending" for b in bookings)))
    return out


def js_i18n():
    """A calendar.js szövegei az aktuális nyelven ({d}, {t} helyőrzőket a JS tölti ki)."""
    o, c = i18n.CAL[lang()]["quote"]
    return {
        "h": _("óra"), "min": _("perc"), "qOpen": o, "qClose": c,
        "minWarn": _("Legalább {d} hosszú foglalás szükséges."),
        "maxWarn": _("Legfeljebb {d} hosszú foglalás lehetséges."),
        "bookBtn": _("{t} lefoglalása"),
        "blocked": _("Nem foglalható"),
        "delSeries": _("Ez egy ismétlődő / több napos tiltás – MINDEN érintett napról törlődik. Biztosan törlöd?"),
        "delOne": _("Biztosan törlöd ezt a tiltást?"),
    }


@app.context_processor
def inject_globals():
    cal = i18n.CAL[lang()]
    return dict(
        app_title=APP_TITLE or _("Időpontfoglaló"), user=g.get("user"), csrf_token=csrf_token,
        _=_, lang=lang(), LANGS=LANGS, q=lambda t: i18n.quote(t, lang()),
        WEEKDAYS=cal["weekdays"], WEEKDAYS_SHORT=cal["weekdays_short"],
        STATUS_LABELS={k: _(v) for k, v in STATUS_LABELS.items()},
        fmt_date=fmt_date, fmt_date_long=fmt_date_long, today=now_local().date(),
        GRID=GRID, MIN_BOOKING=MIN_BOOKING, MAX_BOOKING=MAX_BOOKING, js_i18n=js_i18n,
        pending_count=(db().execute("SELECT COUNT(*) FROM bookings WHERE status='pending'")
                       .fetchone()[0] if g.get("user") and g.user["is_admin"] else 0),
    )


@app.template_filter("d")
def _filter_date(s):
    return i18n.fmt_date_wd(date.fromisoformat(s), lang())


# --------------------------------------------------------------------------
# Auth + CSRF
# --------------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    g.lang = request.cookies.get("lang") if request.cookies.get("lang") in LANGS else DEFAULT_LANG
    if request.endpoint in ("static", "healthz"):
        return
    uid = session.get("uid")
    if uid:
        g.user = db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        token = request.form.get("_csrf", "")
        if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
            abort(400, _("Érvénytelen űrlap (CSRF). Töltsd újra az oldalt."))


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not g.user["is_admin"]:
            abort(403)
        return f(*a, **kw)
    return wrapper


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        row = db().execute("SELECT * FROM users WHERE username = ? AND active = 1",
                           (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            csrf = session.get("_csrf")
            session.clear()
            session["_csrf"] = csrf or secrets.token_urlsafe(32)
            session["uid"] = row["id"]
            session.permanent = True
            audit("login", user=row)
            db().commit()
            return redirect(_safe_next(request.args.get("next")))
        audit("login_failed", {"username": username[:50]}, user=row)
        db().commit()
        log.warning("Failed login for username %r from %s", username[:50], request.remote_addr)
        time.sleep(1)  # brute-force lassítás
        flash(_("Hibás felhasználónév vagy jelszó."), "error")
    return render_template("login.html")


@app.route("/lang/<code>")
def set_lang(code):
    """Nyelvváltás: cookie-ban tároljuk (1 év), így kijelentkezés után is megmarad."""
    resp = redirect(_safe_next(request.args.get("next")))
    if code in LANGS:
        resp.set_cookie("lang", code, max_age=365 * 24 * 3600, samesite="Lax",
                        secure=COOKIE_SECURE, httponly=True)
    return resp


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Naptár nézetek
# --------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    today = now_local().date()
    view = session.get("view", "day")
    if view == "week":
        return redirect(url_for("week_view", day=today.isoformat()))
    if view == "month":
        return redirect(url_for("month_view", ym=today.strftime("%Y-%m")))
    return redirect(url_for("day_view", day=today.isoformat()))


def _nav(view, cur):
    return dict(
        view=view, cur=cur,
        tabs=[("day", _("Nap"), url_for("day_view", day=cur.isoformat())),
              ("week", _("Hét"), url_for("week_view", day=cur.isoformat())),
              ("month", _("Hónap"), url_for("month_view", ym=cur.strftime("%Y-%m")))])


@app.route("/day/<day>")
@login_required
def day_view(day):
    d = parse_day(day)
    session["view"] = "day"
    days = build_days([d])
    week_start = d - timedelta(days=d.weekday())
    strip = [dict(date=wd, blocked=any(r for r in rules_for_day(wd) if not r["time_from"]))
             for wd in (week_start + timedelta(days=i) for i in range(7))]
    return render_template(
        "calendar.html", days=days, strip=strip,
        title=fmt_date_long(d),
        prev_url=url_for("day_view", day=(d - timedelta(days=1)).isoformat()),
        next_url=url_for("day_view", day=(d + timedelta(days=1)).isoformat()),
        today_url=url_for("day_view", day=now_local().date().isoformat()),
        **_nav("day", d))


@app.route("/week/<day>")
@login_required
def week_view(day):
    d = parse_day(day)
    session["view"] = "week"
    ws = d - timedelta(days=d.weekday())
    we = ws + timedelta(days=6)
    days = build_days([ws + timedelta(days=i) for i in range(7)])
    title = i18n.fmt_week(ws, we, lang())
    return render_template(
        "calendar.html", days=days, strip=None, title=title,
        prev_url=url_for("week_view", day=(ws - timedelta(days=7)).isoformat()),
        next_url=url_for("week_view", day=(ws + timedelta(days=7)).isoformat()),
        today_url=url_for("week_view", day=now_local().date().isoformat()),
        **_nav("week", d))


@app.route("/month/<ym>")
@login_required
def month_view(ym):
    try:
        first = datetime.strptime(ym, "%Y-%m").date()
    except ValueError:
        abort(404)
    session["view"] = "month"
    today = now_local().date()
    start = first - timedelta(days=first.weekday())
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = nxt - timedelta(days=1)
    end = last + timedelta(days=6 - last.weekday())
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = build_days(dates)
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    prev = (first - timedelta(days=1)).replace(day=1)
    cur = today if (today.year, today.month) == (first.year, first.month) else first
    return render_template(
        "month.html", weeks=weeks, month=first, title=i18n.fmt_month(first, lang()),
        prev_url=url_for("month_view", ym=prev.strftime("%Y-%m")),
        next_url=url_for("month_view", ym=nxt.strftime("%Y-%m")),
        today_url=url_for("month_view", ym=today.strftime("%Y-%m")),
        **_nav("month", cur))


# --------------------------------------------------------------------------
# Foglalás
# --------------------------------------------------------------------------
@app.post("/book")
@login_required
def book():
    d = parse_day(request.form.get("day"))
    start, end = request.form.get("start", ""), request.form.get("end", "")
    back = redirect(_safe_next(request.form.get("next")) if request.form.get("next")
                    else url_for("day_view", day=d.isoformat()))

    def fail(msg):
        flash(msg, "error")
        return back

    if start not in GRID_STARTS or end not in GRID_ENDS or start >= end:
        return fail(_("Érvénytelen időtartam."))
    dur = _to_min(end) - _to_min(start)
    is_admin = bool(g.user["is_admin"])
    if not is_admin and dur < MIN_BOOKING:
        return fail(_("A foglalás legalább {d} legyen.", d=fmt_duration(MIN_BOOKING)))
    if not is_admin and MAX_BOOKING and dur > MAX_BOOKING:
        return fail(_("A foglalás legfeljebb {d} lehet.", d=fmt_duration(MAX_BOOKING)))
    now = now_local()
    if _dt(d, start) <= now:
        return fail(_("Múltbeli időpontra nem lehet foglalni."))
    if d > now.date() + timedelta(days=DAYS_AHEAD):
        return fail(_("Legfeljebb {n} napra előre lehet foglalni.", n=DAYS_AHEAD))
    if slot_block(rules_for_day(d), start, end):
        return fail(_("A kijelölt időtartam tiltott időszakot érint."))

    conn = db()
    with _write_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if MAX_ACTIVE_PER_USER and not is_admin:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM bookings WHERE user_id = ? AND status IN "
                    "('pending','approved') AND day >= ?",
                    (g.user["id"], now.date().isoformat())).fetchone()[0]
                if cnt >= MAX_ACTIVE_PER_USER:
                    conn.rollback()
                    return fail(_("Egyszerre legfeljebb {n} aktív foglalásod lehet.", n=MAX_ACTIVE_PER_USER))
            clash = conn.execute(
                "SELECT 1 FROM bookings WHERE day = ? AND status IN ('pending','approved') "
                "AND start < ? AND end > ?", (d.isoformat(), end, start)).fetchone()
            if clash:
                conn.rollback()
                return fail(_("A kijelölt időtartam (egy része) már foglalt."))
            status = "approved" if (is_admin or not REQUIRE_APPROVAL) else "pending"
            ts = now.isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO bookings (user_id, day, start, end, status, note, created_at, decided_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], d.isoformat(), start, end, status,
                 request.form.get("note", "").strip()[:200] or None, ts,
                 ts if status == "approved" else None))
            note = request.form.get("note", "").strip()[:200]
            audit("book", booking_details({"day": d.isoformat(), "start": start, "end": end},
                                          auto=status == "approved", note=note))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    flash(_("Foglalás rögzítve: {t} – jóváhagyásra vár.", t=f"{start}–{end}") if status == "pending"
          else _("Foglalás rögzítve: {t}.", t=f"{start}–{end}"), "ok")
    return back


@app.post("/booking/<int:bid>/cancel")
@login_required
def cancel_booking(bid):
    b = _booking_with_owner(bid)
    if b is None:
        abort(404)
    # Csak a saját foglalását mondhatja le (az admin bárkiét)
    if b["user_id"] != g.user["id"] and not g.user["is_admin"]:
        abort(403)
    if b["status"] not in ACTIVE:
        flash(_("Ez a foglalás már nem aktív."), "error")
    else:
        db().execute("UPDATE bookings SET status = 'cancelled', decided_at = ? WHERE id = ?",
                     (now_local().isoformat(timespec="seconds"), bid))
        mine = b["user_id"] == g.user["id"]
        audit("cancel", booking_details(b, None if mine else b["display_name"]))
        db().commit()
        flash(_("Foglalás lemondva."), "ok")
    return redirect(_safe_next(request.form.get("next")))


@app.route("/my")
@login_required
def my_bookings():
    """Foglalások listája: a user összes saját foglalása; az admin a „Mindenki” nézetben mindenkiét."""
    now = now_local()
    is_admin = bool(g.user["is_admin"])
    scope = "all" if is_admin and request.args.get("scope") == "all" else "mine"
    f_status = request.args.get("status", "")
    if f_status not in MY_FILTERS:
        f_status = ""
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    params = {"uid": g.user["id"]}
    scope_sql = "b.user_id = :uid" if scope == "mine" else "1"
    status_sql = "1"
    if f_status:
        sts = MY_FILTERS[f_status][1]
        status_sql = "b.status IN (" + ",".join(f":s{i}" for i in range(len(sts))) + ")"
        params.update({f"s{i}": v for i, v in enumerate(sts)})

    # Szűrő-chipekhez darabszámok (a státusz-szűrő nélkül)
    counts = dict(db().execute(
        f"SELECT b.status, COUNT(*) FROM bookings b WHERE {scope_sql} GROUP BY b.status",
        params).fetchall())
    filters = [(key, _(label), sum(counts.get(s, 0) for s in sts))
               for key, (label, sts) in MY_FILTERS.items()]
    total_all = sum(counts.values())

    # Közelgő = aktív és még nem ért véget; ezek elöl, időrendben.
    # Utánuk minden más (lezajlott, lemondott, elutasított), fordított időrendben.
    params.update(d=now.date().isoformat(), t=now.strftime("%H:%M"),
                  lim=MY_PAGE_SIZE, off=(page - 1) * MY_PAGE_SIZE)
    up = "(b.status IN ('pending','approved') AND (b.day > :d OR (b.day = :d AND b.end > :t)))"
    where = f"WHERE {scope_sql} AND {status_sql}"
    total = db().execute(f"SELECT COUNT(*) FROM bookings b {where}", params).fetchone()[0]
    rows = db().execute(
        f"SELECT b.*, u.display_name, {up} AS upcoming FROM bookings b "
        f"JOIN users u ON u.id = b.user_id {where} "
        f"ORDER BY upcoming DESC, CASE WHEN {up} THEN b.day || b.start END ASC, "
        f"b.day DESC, b.start DESC LIMIT :lim OFFSET :off", params).fetchall()

    items = []
    for r in rows:
        started = _dt(date.fromisoformat(r["day"]), r["start"]) <= now
        can_decide = is_admin and r["status"] == "pending" and not started
        items.append(dict(r, can_cancel=(r["status"] in ACTIVE and not started and not can_decide
                                         and (r["user_id"] == g.user["id"] or is_admin)),
                          can_decide=can_decide))
    pages = max(1, -(-total // MY_PAGE_SIZE))

    def page_url(p, **over):
        args = {"scope": scope if scope == "all" else None, "status": f_status or None, "page": p}
        args.update(over)
        return url_for("my_bookings", **{k: v for k, v in args.items() if v and v != 1})
    return render_template("my.html", items=items, scope=scope, f_status=f_status, filters=filters,
                           total_all=total_all, page=page, pages=pages, page_url=page_url)


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin():
    today = now_local().date().isoformat()
    q = ("SELECT b.*, u.display_name FROM bookings b JOIN users u ON u.id = b.user_id "
         "WHERE b.status = ? AND b.day >= ? ORDER BY b.day, b.start")
    pending = db().execute(q, ("pending", today)).fetchall()
    approved = db().execute(q + " LIMIT 100", ("approved", today)).fetchall()
    conflicts = set()
    for b in list(pending) + list(approved):
        if slot_block(rules_for_day(date.fromisoformat(b["day"])), b["start"], b["end"]):
            conflicts.add(b["id"])
    return render_template("admin.html", pending=pending, approved=approved, conflicts=conflicts)


@app.post("/admin/booking/<int:bid>/<action>")
@admin_required
def admin_decide(bid, action):
    if action not in ("approve", "reject"):
        abort(404)
    new_status = "approved" if action == "approve" else "rejected"
    cur = db().execute(
        "UPDATE bookings SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
        (new_status, now_local().isoformat(timespec="seconds"), bid))
    if cur.rowcount:
        b = _booking_with_owner(bid)
        audit(action, booking_details(b, b["display_name"]))
    db().commit()
    if cur.rowcount:
        flash(_("Jóváhagyva.") if action == "approve" else _("Elutasítva."), "ok")
    else:
        flash(_("A foglalás már nem függőben lévő."), "error")
    return redirect(_safe_next(request.form.get("next")))


@app.post("/admin/approve-all")
@admin_required
def admin_approve_all():
    rows = db().execute("SELECT b.*, u.display_name FROM bookings b JOIN users u ON u.id = b.user_id "
                        "WHERE b.status = 'pending' ORDER BY b.day, b.start").fetchall()
    cur = db().execute("UPDATE bookings SET status='approved', decided_at=? WHERE status='pending'",
                       (now_local().isoformat(timespec="seconds"),))
    for b in rows:
        audit("approve", booking_details(b, b["display_name"], bulk=True))
    db().commit()
    flash(_("{n} foglalás jóváhagyva.", n=cur.rowcount), "ok")
    return redirect(url_for("admin"))


def _valid_hhmm(v):
    try:
        datetime.strptime(v, "%H:%M")
        return True
    except (TypeError, ValueError):
        return False


@app.route("/admin/rules", methods=["GET", "POST"])
@admin_required
def admin_rules():
    if request.method == "POST":
        f = request.form
        weekdays = sorted({int(x) for x in f.getlist("weekdays") if x in "0123456" and x})
        date_from = f.get("date_from") or None
        date_to = f.get("date_to") or None
        whole_day = f.get("whole_day") == "1"
        time_from = None if whole_day else (f.get("time_from") or None)
        time_to = None if whole_day else (f.get("time_to") or None)
        reason = f.get("reason", "").strip()[:200] or None
        err = None
        try:
            for v in (date_from, date_to):
                if v:
                    date.fromisoformat(v)
        except ValueError:
            err = _("Érvénytelen dátum.")
        if not err and any(v and not _valid_hhmm(v) for v in (time_from, time_to)):
            err = _("Érvénytelen időpont.")
        if not err and date_from and date_to and date_from > date_to:
            err = _("A kezdő dátum nem lehet későbbi a záró dátumnál.")
        if not err and not whole_day and (not time_from or not time_to or time_from >= time_to):
            err = _("Adj meg érvényes időtartományt, vagy válaszd az „egész nap” opciót.")
        if not err and not weekdays and not date_from and not date_to:
            err = _("Adj meg legalább egy napot a héten vagy egy dátumot/időszakot.")
        if err:
            flash(err, "error")
            return render_template("rules.html", rules=_all_rules(), form=f)
        _add_rule(date_from, date_to, ",".join(map(str, weekdays)) or None,
                  time_from, time_to, reason)
        return redirect(url_for("admin_rules"))
    return render_template("rules.html", rules=_all_rules(), form={})


def _all_rules():
    rows = db().execute("SELECT * FROM block_rules ORDER BY id DESC").fetchall()
    return [dict(r, text=describe_rule(r)) for r in rows]


def _add_rule(date_from, date_to, weekdays, time_from, time_to, reason):
    db().execute(
        "INSERT INTO block_rules (date_from, date_to, weekdays, time_from, time_to, reason, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date_from, date_to, weekdays, time_from, time_to, reason,
         now_local().isoformat(timespec="seconds")))
    audit("rule_add", rule_details(dict(date_from=date_from, date_to=date_to, weekdays=weekdays,
                                        time_from=time_from, time_to=time_to), reason))
    db().commit()
    today = now_local().date().isoformat()
    affected = 0
    for b in db().execute("SELECT * FROM bookings WHERE status IN ('pending','approved') "
                          "AND day >= ?", (today,)):
        if slot_block(rules_for_day(date.fromisoformat(b["day"])), b["start"], b["end"]):
            affected += 1
    if affected:
        flash(_("Tiltás létrehozva. Figyelem: {n} meglévő foglalás tiltott időszakba esik – lásd az Admin oldalon.",
                n=affected), "warn")
    else:
        flash(_("Tiltás létrehozva."), "ok")


@app.post("/admin/rules/<int:rid>/delete")
@admin_required
def admin_rule_delete(rid):
    r = db().execute("SELECT * FROM block_rules WHERE id = ?", (rid,)).fetchone()
    if r is None:
        flash(_("Ez a tiltás már nem létezik."), "error")
        return redirect(_safe_next(request.form.get("next") or url_for("admin_rules")))
    db().execute("DELETE FROM block_rules WHERE id = ?", (rid,))
    audit("rule_delete", rule_details(r, r["reason"]))
    db().commit()
    flash(_("Tiltás törölve."), "ok")
    return redirect(_safe_next(request.form.get("next") or url_for("admin_rules")))


@app.post("/admin/quick-block")
@admin_required
def admin_quick_block():
    """Gyors tiltás a naptárból: kijelölt időtartam vagy egész nap."""
    d = parse_day(request.form.get("day"))
    start, end = request.form.get("start") or None, request.form.get("end") or None
    if (start or end) and not (_valid_hhmm(start) and _valid_hhmm(end) and start < end):
        abort(400, _("Érvénytelen időtartam."))
    _add_rule(d.isoformat(), d.isoformat(), None, start, end,
              request.form.get("reason", "").strip()[:200] or None)
    return redirect(_safe_next(request.form.get("next"))
                    if request.form.get("next") else url_for("day_view", day=d.isoformat()))


@app.route("/admin/log")
@admin_required
def admin_log():
    f_user = request.args.get("user", "")
    f_action = request.args.get("action", "")
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    where, params = [], []
    if f_user.isdigit():
        where.append("user_id = ?")
        params.append(int(f_user))
    if f_action in LOG_ACTIONS:
        where.append("action = ?")
        params.append(f_action)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = db().execute(f"SELECT COUNT(*) FROM audit_log{sql_where}", params).fetchone()[0]
    rows = db().execute(f"SELECT * FROM audit_log{sql_where} ORDER BY id DESC LIMIT ? OFFSET ?",
                        params + [LOG_PAGE_SIZE, (page - 1) * LOG_PAGE_SIZE]).fetchall()
    entries = []
    for r in rows:
        ts = datetime.fromisoformat(r["ts"])
        entries.append(dict(r, date=fmt_date(ts.date()), time=ts.strftime("%H:%M:%S"),
                            label=_(LOG_ACTIONS.get(r["action"], r["action"])),
                            details=log_details(r["action"], r["details"])))
    users = db().execute("SELECT id, display_name, active FROM users ORDER BY display_name").fetchall()
    pages = max(1, -(-total // LOG_PAGE_SIZE))

    def page_url(p):
        return url_for("admin_log", page=p, **{k: v for k, v in
                                               (("user", f_user), ("action", f_action)) if v})
    return render_template("log.html", entries=entries, users=users,
                           actions={k: _(v) for k, v in LOG_ACTIONS.items()},
                           f_user=f_user, f_action=f_action, page=page, pages=pages, total=total,
                           page_url=page_url)


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, msg=_("Nincs jogosultságod ehhez.")), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, msg=_("Az oldal nem található.")), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, msg=e.description), 400


@app.route("/healthz")
def healthz():
    return "ok"


init_db()
