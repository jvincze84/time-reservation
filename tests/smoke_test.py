"""Végponttól végpontig tartó füstteszt (csak standard könyvtár).

NE futtasd az éles példány ellen! Használd a tests/run.sh-t, ami egy eldobható
konténert indít üres adatbázissal és a config/users.example.json felhasználóival.

    BASE_URL=http://127.0.0.1:8091 python3 tests/smoke_test.py
"""
import datetime as dt
import html
import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8091").rstrip("/")
ADMIN = ("admin", "valtoztasd-meg")
ANNA = ("anna", "anna123")
BELA = ("bela", "bela123")

_failures = []


def check(name, cond, info=""):
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{info}]" if info and not cond else ""))
    if not cond:
        _failures.append(name)


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = None

    def _req(self, path, data=None):
        try:
            r = self.opener.open(BASE + path, data)
            return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def get(self, path):
        return self._req(path)

    def post(self, path, data, token=None):
        if self.token is None:
            self.token = re.search(r'name="_csrf" value="([^"]+)"', self.get("/login")[1]).group(1)
        body = urllib.parse.urlencode({**data, "_csrf": token or self.token}, doseq=True).encode()
        return self._req(path, body)


def login(user):
    c = Client()
    _, h = c.post("/login", {"username": user[0], "password": user[1]})
    return c, h


def flashes(h):
    return [html.unescape(m).strip() for m in re.findall(r'class="flash flash-\w+">([^<]+)', h)]


def booking_ids(h):
    return [int(x) for x in re.findall(r"/booking/(\d+)/cancel", h)]


def main():
    today = dt.date.today()
    mon = today + dt.timedelta(days=7 - today.weekday())        # jövő hétfő
    sat = mon + dt.timedelta(days=5)
    day = mon.isoformat()

    print("Belépés")
    _, h = login(("anna", "rossz"))
    check("rossz jelszó elutasítva", "Hibás felhasználónév" in h)
    anna, h = login(ANNA)
    check("anna belép", "Foglalásaim" in h)
    bela, _ = login(BELA)
    admin, _ = login(ADMIN)

    def book(c, start, end, d=day, **kw):
        return flashes(c.post("/book", {"day": d, "start": start, "end": end,
                                        "next": "/my", **kw})[1])

    print("Foglalás")
    check("10:00–11:30 foglalás", any("rögzítve" in f for f in book(anna, "10:00", "11:30", note="teszt")))
    check("átfedő foglalás tiltva", any("foglalt" in f for f in book(bela, "11:00", "12:00")))
    check("átfogó foglalás tiltva", any("foglalt" in f for f in book(bela, "09:00", "13:00")))
    check("szomszédos foglalás OK", any("rögzítve" in f for f in book(bela, "11:30", "12:00")))
    check("rácson kívüli idő tiltva", any("Érvénytelen" in f for f in book(bela, "12:15", "13:00")))
    check("nulla hossz tiltva", any("Érvénytelen" in f for f in book(bela, "13:00", "13:00")))
    check("nyitás előtti idő tiltva", any("Érvénytelen" in f for f in book(bela, "07:00", "08:30")))
    check("múltbeli nap tiltva", any("Múltbeli" in f for f in book(bela, "10:00", "11:00", d="2020-01-06")))

    print("Jogosultságok")
    _, h = bela.get(f"/day/{day}")
    check("user nem látja más nevét", "Kiss Anna" not in h and "Foglalt" in h)
    anna_bid = booking_ids(anna.get("/my")[1])[0]
    check("user nem mondhatja le másét (403)", bela.post(f"/booking/{anna_bid}/cancel", {})[0] == 403)
    check("user nem hagyhat jóvá (403)", bela.post(f"/admin/booking/{anna_bid}/approve", {})[0] == 403)
    for p in ("/admin", "/admin/rules", "/admin/log"):
        check(f"user: {p} → 403", bela.get(p)[0] == 403)
    check("user ?scope=all hatástalan", "Kiss Anna" not in bela.get("/my?scope=all")[1])
    check("hamis CSRF → 400", anna.post("/book", {"day": day, "start": "14:00", "end": "15:00"},
                                         token="hamis")[0] == 400)

    print("Admin döntések")
    _, h = admin.get("/my?scope=all&status=pending")
    check("admin látja a neveket", "Kiss Anna" in h and "Nagy Béla" in h)
    check("függőnél nincs Lemondás gomb az adminnak", "Lemondás</button>" not in h)
    bela_bid = booking_ids(bela.get("/my")[1])[0]
    check("jóváhagyás", "Jóváhagyva." in flashes(admin.post(f"/admin/booking/{anna_bid}/approve",
                                                          {"next": "/admin"})[1]))
    check("elutasítás", "Elutasítva." in flashes(admin.post(f"/admin/booking/{bela_bid}/reject",
                                                           {"next": "/admin"})[1]))
    check("anna látja: Jóváhagyva", "Jóváhagyva" in anna.get("/my")[1])
    check("admin lemondhat jóváhagyottat",
          "Foglalás lemondva." in flashes(admin.post(f"/booking/{anna_bid}/cancel", {"next": "/my"})[1]))
    check("admin foglalása azonnal jóváhagyott",
          any("rögzítve: 16:00–17:00." in f for f in book(admin, "16:00", "17:00")))

    print("Tiltások")
    h = admin.post("/admin/rules", {"weekdays": ["5", "6"], "whole_day": "1", "reason": "Hétvége"})[1]
    check("hétvégi sorozat létrehozva", any("Tiltás létrehozva" in f for f in flashes(h)))
    check("szombati foglalás tiltva", any("tiltott" in f for f in book(anna, "10:00", "11:00", d=sat.isoformat())))
    admin.post("/admin/quick-block", {"day": day, "start": "14:00", "end": "15:30", "next": "/admin/rules"})
    check("tiltásba lógó foglalás tiltva", any("tiltott" in f for f in book(anna, "15:00", "16:00")))
    rid = re.findall(r"/admin/rules/(\d+)/delete", admin.get("/admin/rules")[1])[0]
    check("tiltás törlése", "Tiltás törölve." in flashes(admin.post(f"/admin/rules/{rid}/delete", {})[1]))

    print("Nézetek")
    for c, who in ((anna, "anna"), (admin, "admin")):
        for p in (f"/day/{day}", f"/week/{day}", f"/month/{day[:7]}", "/my"):
            check(f"{who}: {p} → 200", c.get(p)[0] == 200)
    for p in ("/admin", "/admin/rules", "/admin/log", "/my?scope=all&status=closed"):
        check(f"admin: {p} → 200", admin.get(p)[0] == 200)
    _, h = admin.get(f"/week/{day}")
    check("hét nézet: 7 oszlop", h.count('class="tg-col') == 7)
    check("rossz dátum → 404", anna.get("/day/2026-13-01")[0] == 404)

    print("Napló")
    _, h = admin.get("/admin/log")
    for label in ("Belépés", "Sikertelen belépés", "Foglalás", "Jóváhagyás", "Elutasítás",
                  "Lemondás / törlés", "Tiltás létrehozva", "Tiltás törölve"):
        check(f"naplóban: {label}", f'log-pill">{label}<' in h)

    print("Többnyelvűség")
    c = Client()
    _, h = c.get("/login")
    check("alapértelmezett nyelv: magyar", 'lang="hu"' in h and "Felhasználónév" in h)
    _, h = c.get("/lang/en?next=/login")
    check("átváltás angolra", 'lang="en"' in h and "Username" in h and "Sign in" in h)
    _, h = c.get("/lang/xx?next=/login")
    check("ismeretlen nyelvkód figyelmen kívül", 'lang="en"' in h)
    _, h = c.post("/login", {"username": "anna", "password": "rossz"})
    check("angol hibaüzenet", "Incorrect username or password." in flashes(h))
    _, h = c.post("/login", {"username": ANNA[0], "password": ANNA[1]})
    check("angol menü", "My bookings" in h and "Calendar" in h)
    h = flashes(c.post("/book", {"day": day, "start": "18:00", "end": "19:30", "next": "/my"})[1])
    check("angol foglalás-üzenet", any(f.startswith("Booking saved: 18:00–19:30") for f in h), h)
    _, h = c.get(f"/day/{day}")
    check("angol nap nézet", f"Monday, {mon.strftime('%b')} {mon.day}, {mon.year}" in h and ">Week<" in h)
    check("JS szövegek angolul", 'window.I18N = {' in h and '"bookBtn": "Book {t}"' in h)
    _, h = c.get(f"/month/{day[:7]}")
    check("angol hónap cím", f"{mon.strftime('%B')} {mon.year}" in h and ">Mon<" in h)
    _, h = c.get("/my")
    check("angol státusz", "Pending approval" in h and "Upcoming" in h)
    c.get("/lang/hu?next=/my")
    _, h = c.get("/my")
    check("vissza magyarra", "Foglalásaim" in h and "Jóváhagyásra vár" in h)

    print("Napló két nyelven")
    admin.get("/lang/en?next=/admin/log")
    _, h = admin.get("/admin/log")
    check("napló angol címkék", 'log-pill">Failed sign-in<' in h and 'log-pill">Block created<' in h)
    check("napló angol részletek", "Username: rossz" in h or "Username: anna" in h)
    check("napló angol tiltás leírás", "Every Saturday, Sunday, all day" in h)
    admin.get("/lang/hu?next=/admin/log")
    _, h = admin.get("/admin/log")
    check("napló magyar részletek", "Felhasználónév: anna" in h and "Minden szombat, vasárnap, egész nap" in h)

    print()
    if _failures:
        print(f"SIKERTELEN: {len(_failures)} ellenőrzés")
        sys.exit(1)
    print("MINDEN ELLENŐRZÉS SIKERES")


if __name__ == "__main__":
    main()
