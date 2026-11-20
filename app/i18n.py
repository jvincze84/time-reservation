"""Többnyelvűség (i18n): magyar (forrásnyelv) + angol.

A kódban és a sablonokban a magyar szöveg maga a kulcs: _("Foglalásaim").
Angolra az EN szótár fordít; ha egy kulcs hiányzik, a magyar szöveg jelenik meg.
A {név} helyőrzőket a translate() tölti ki: _("Legfeljebb {n} napra előre lehet foglalni.", n=60).

Új szöveg felvételekor az angol fordítást is add hozzá az EN szótárhoz;
a tests/i18n_check.py jelzi, ha valamelyik hiányzik.
"""
from datetime import date

LANGS = {"hu": "Magyar", "en": "English"}
DEFAULT_LANG = "hu"


def N_(text):
    """Jelölő: a szöveg fordítandó, de csak megjelenítéskor fordítjuk (pl. modul szintű címkék)."""
    return text


CAL = {
    "hu": dict(
        weekdays=["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"],
        weekdays_short=["H", "K", "Sze", "Cs", "P", "Szo", "V"],
        months=["jan.", "febr.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.",
                "szept.", "okt.", "nov.", "dec."],
        months_full=["január", "február", "március", "április", "május", "június", "július",
                     "augusztus", "szeptember", "október", "november", "december"],
        quote=("„", "”"),
    ),
    "en": dict(
        weekdays=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        weekdays_short=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        months=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        months_full=["January", "February", "March", "April", "May", "June", "July",
                     "August", "September", "October", "November", "December"],
        quote=("“", "”"),
    ),
}


def translate(text, lang, **kw):
    s = EN.get(text, text) if lang == "en" else text
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- dátum/idő formázás
def fmt_date(d: date, lang):
    """2026. nov. 9.  |  Nov 9, 2026"""
    m = CAL[lang]["months"][d.month - 1]
    return f"{d.year}. {m} {d.day}." if lang == "hu" else f"{m} {d.day}, {d.year}"


def fmt_date_long(d: date, lang):
    """Hétfő, 2026. nov. 9.  |  Monday, Nov 9, 2026"""
    return f"{CAL[lang]['weekdays'][d.weekday()]}, {fmt_date(d, lang)}"


def fmt_date_wd(d: date, lang):
    """2026. nov. 9. hétfő  |  Mon, Nov 9, 2026"""
    if lang == "hu":
        return f"{fmt_date(d, lang)} {CAL[lang]['weekdays'][d.weekday()].lower()}"
    return f"{CAL[lang]['weekdays_short'][d.weekday()]}, {fmt_date(d, lang)}"


def fmt_week(ws: date, we: date, lang):
    """Egy hét címe, pl. 2026. nov. 2–8.  |  Nov 2–8, 2026"""
    ms = CAL[lang]["months"]
    if lang == "hu":
        if ws.year != we.year:
            return f"{fmt_date(ws, lang)} – {fmt_date(we, lang)}"
        if ws.month != we.month:
            return f"{fmt_date(ws, lang)} – {ms[we.month - 1]} {we.day}."
        return f"{ws.year}. {ms[ws.month - 1]} {ws.day}–{we.day}."
    if ws.year != we.year:
        return f"{fmt_date(ws, lang)} – {fmt_date(we, lang)}"
    if ws.month != we.month:
        return f"{ms[ws.month - 1]} {ws.day} – {ms[we.month - 1]} {we.day}, {we.year}"
    return f"{ms[ws.month - 1]} {ws.day}–{we.day}, {ws.year}"


def fmt_month(first: date, lang):
    """2026. november  |  November 2026"""
    m = CAL[lang]["months_full"][first.month - 1]
    return f"{first.year}. {m}" if lang == "hu" else f"{m} {first.year}"


def fmt_duration(minutes, lang):
    """1 óra 30 perc  |  1 h 30 min"""
    h, m = divmod(minutes, 60)
    parts = []
    if h:
        parts.append(f"{h} {translate(N_('óra'), lang)}")
    if m:
        parts.append(f"{m} {translate(N_('perc'), lang)}")
    return " ".join(parts)


def quote(text, lang):
    o, c = CAL[lang]["quote"]
    return f"{o}{text}{c}"


def describe_rule(r, lang):
    """Egy tiltási szabály olvasható leírása (r: dict vagy sqlite3.Row)."""
    parts = []
    if r["weekdays"]:
        days = [CAL[lang]["weekdays"][int(x)] for x in r["weekdays"].split(",")]
        if lang == "hu":
            parts.append("Minden " + ", ".join(d.lower() for d in days))
        else:
            parts.append("Every " + ", ".join(days))
    if r["date_from"] and r["date_from"] == r["date_to"]:
        parts.append(fmt_date(date.fromisoformat(r["date_from"]), lang))
    else:
        if r["date_from"]:
            d = fmt_date(date.fromisoformat(r["date_from"]), lang)
            parts.append(f"{d}-tól" if lang == "hu" else f"from {d}")
        if r["date_to"]:
            d = fmt_date(date.fromisoformat(r["date_to"]), lang)
            parts.append(f"{d}-ig" if lang == "hu" else f"until {d}")
    if not r["weekdays"] and not r["date_from"] and not r["date_to"]:
        parts.append(translate(N_("Minden nap"), lang))
    parts.append(f"{r['time_from']}–{r['time_to']}" if r["time_from"] else translate(N_("egész nap"), lang))
    return ", ".join(parts)


# ---------------------------------------------------------------- angol fordítások
EN = {
    # --- általános, navigáció
    "Időpontfoglaló": "Booking",
    "Naptár": "Calendar",
    "Foglalásaim": "My bookings",
    "Admin": "Admin",
    "Tiltások": "Blocks",
    "Napló": "Log",
    "Nyelv": "Language",
    "Kijelentkezés": "Sign out",
    "Kilépés": "Sign out",
    "Bezárás": "Close",
    "Vissza a naptárhoz": "Back to calendar",
    "Nincs jogosultságod ehhez.": "You don't have permission to do this.",
    "Az oldal nem található.": "Page not found.",
    "Érvénytelen űrlap (CSRF). Töltsd újra az oldalt.": "Invalid form (CSRF). Please reload the page.",

    # --- belépés
    "Bejelentkezés": "Sign in",
    "Felhasználónév": "Username",
    "Jelszó": "Password",
    "Belépés": "Sign in",
    "Hibás felhasználónév vagy jelszó.": "Incorrect username or password.",

    # --- naptár
    "Nap": "Day",
    "Hét": "Week",
    "Hónap": "Month",
    "Ma": "Today",
    "Ugrás dátumra": "Go to date",
    "Előző": "Previous",
    "Következő": "Next",
    "Szabad": "Free",
    "Saját": "Mine",
    "Foglalt": "Booked",
    "Tiltott": "Blocked",
    "Tiltva": "Blocked",
    "Nem foglalható": "Not available",
    "Jelölj ki egy időtartamot egérrel húzva, vagy kattints a kezdetre, majd Shift+kattints a végére.":
        "Select a time range by dragging with the mouse, or click the start and Shift+click the end.",
    "Koppints a kezdő, majd a záró időpontra – vagy nyomd hosszan, és húzd az ujjad.":
        "Tap the start time, then the end time – or long-press and drag your finger.",
    "Szabad idősávok: {n}": "Free slots: {n}",
    "A sáv a nap telítettségét mutatja (foglalt, tiltott vagy elmúlt idő). Koppints egy napra a részletekért.":
        "The bar shows how full the day is (booked, blocked or past time). Tap a day for details.",
    "óra": "h",
    "perc": "min",
    "Legalább {d} hosszú foglalás szükséges.": "Bookings must be at least {d} long.",
    "Legfeljebb {d} hosszú foglalás lehetséges.": "Bookings can be at most {d} long.",
    "{t} lefoglalása": "Book {t}",
    "Megjegyzés (opcionális)": "Note (optional)",
    "Foglalás": "Booking",
    "Indok (opcionális)": "Reason (optional)",
    "Tiltás indoka (opcionális)": "Reason for blocking (optional)",
    "Tiltás": "Block",
    "Egész nap tiltása": "Block whole day",
    "Az egész napot letiltod?": "Block the whole day?",
    "Ez egy ismétlődő / több napos tiltás – MINDEN érintett napról törlődik. Biztosan törlöd?":
        "This is a recurring / multi-day block – it will be removed from ALL affected days. Delete it?",
    "Biztosan törlöd ezt a tiltást?": "Delete this block?",
    "Tiltás törlése": "Delete block",

    # --- foglalás állapotai, műveletek
    "Jóváhagyásra vár": "Pending approval",
    "Jóváhagyva": "Approved",
    "Elutasítva": "Rejected",
    "Lemondva": "Cancelled",
    "Jóváhagy": "Approve",
    "Elutasít": "Reject",
    "Jóváhagyás": "Approve",
    "Elutasítás": "Reject",
    "Lemondás": "Cancel",
    "Törlés": "Delete",
    "Biztosan lemondod / törlöd ezt a foglalást?": "Cancel / delete this booking?",
    "Biztosan törlöd ezt a foglalást?": "Delete this booking?",

    # --- foglalás üzenetei
    "Érvénytelen időtartam.": "Invalid time range.",
    "A foglalás legalább {d} legyen.": "Bookings must be at least {d} long.",
    "A foglalás legfeljebb {d} lehet.": "Bookings can be at most {d} long.",
    "Múltbeli időpontra nem lehet foglalni.": "You can't book a time in the past.",
    "Legfeljebb {n} napra előre lehet foglalni.": "You can book at most {n} days in advance.",
    "A kijelölt időtartam tiltott időszakot érint.": "The selected time range overlaps a blocked period.",
    "Egyszerre legfeljebb {n} aktív foglalásod lehet.": "You can have at most {n} active bookings at a time.",
    "A kijelölt időtartam (egy része) már foglalt.": "The selected time range is (partly) already booked.",
    "Foglalás rögzítve: {t} – jóváhagyásra vár.": "Booking saved: {t} – pending approval.",
    "Foglalás rögzítve: {t}.": "Booking saved: {t}.",
    "Ez a foglalás már nem aktív.": "This booking is no longer active.",
    "Foglalás lemondva.": "Booking cancelled.",
    "Jóváhagyva.": "Approved.",
    "Elutasítva.": "Rejected.",
    "A foglalás már nem függőben lévő.": "This booking is no longer pending.",
    "{n} foglalás jóváhagyva.": "Bookings approved: {n}.",

    # --- Foglalásaim
    "Minden foglalás": "All bookings",
    "Mindenki": "Everyone",
    "Mind": "All",
    "Aktív": "Active",
    "Lemondva / elutasítva": "Cancelled / rejected",
    "Nincs ilyen foglalás.": "No bookings found.",
    "Foglalj most!": "Book now!",
    "Közelgő": "Upcoming",
    "Korábbi és lezárt": "Past and closed",

    # --- Admin
    "Jóváhagyásra vár – minden felhasználó": "Pending approval – all users",
    "Mindet jóváhagyod?": "Approve all?",
    "Mind ✓": "All ✓",
    "Nincs függőben lévő foglalás.": "No pending bookings.",
    "Tiltott időszakba esik": "Falls within a blocked period",
    "Minden felhasználó közelgő jóváhagyott foglalásai": "Upcoming approved bookings – all users",
    "Összes foglalás": "All bookings",

    # --- Tiltások
    "Új tiltás": "New block",
    "Mely napokon?": "On which days?",
    "üresen hagyva: minden nap a megadott időszakban": "leave empty: every day in the given period",
    "Hétvége": "Weekend",
    "Hétköznapok": "Weekdays",
    "Időszak": "Period",
    "üresen hagyva: határozatlan ideig": "leave empty: indefinitely",
    "Ettől": "From",
    "Eddig": "Until",
    "Napszak": "Time of day",
    "Egész nap": "All day",
    "egész nap": "all day",
    "Minden nap": "Every day",
    "Kezdete": "Start",
    "Vége": "End",
    "Indok (opcionális, a felhasználók is látják)": "Reason (optional, visible to users)",
    "pl. Zárva, szabadság, karbantartás": "e.g. Closed, holiday, maintenance",
    "Tiltás mentése": "Save block",
    "Aktív tiltások": "Active blocks",
    "Nincs tiltás.": "No blocks.",
    "Törlöd a tiltást?": "Delete this block?",
    "Érvénytelen dátum.": "Invalid date.",
    "Érvénytelen időpont.": "Invalid time.",
    "A kezdő dátum nem lehet későbbi a záró dátumnál.": "The start date can't be later than the end date.",
    "Adj meg érvényes időtartományt, vagy válaszd az „egész nap” opciót.":
        "Enter a valid time range, or choose the “all day” option.",
    "Adj meg legalább egy napot a héten vagy egy dátumot/időszakot.":
        "Select at least one weekday or a date / period.",
    "Tiltás létrehozva.": "Block created.",
    "Tiltás létrehozva. Figyelem: {n} meglévő foglalás tiltott időszakba esik – lásd az Admin oldalon.":
        "Block created. Warning: existing bookings now in a blocked period: {n} – see the Admin page.",
    "Ez a tiltás már nem létezik.": "This block no longer exists.",
    "Tiltás törölve.": "Block deleted.",

    # --- Napló
    "Felhasználó": "User",
    "inaktív": "inactive",
    "Művelet": "Action",
    "Szűrés": "Filter",
    "Szűrés törlése": "Clear filter",
    "Nincs bejegyzés.": "No entries.",
    "Ismeretlen": "Unknown",
    "Újabbak": "Newer",
    "Régebbiek": "Older",
    "Sikertelen belépés": "Failed sign-in",
    "Lemondás / törlés": "Cancellation",
    "Tiltás létrehozva": "Block created",
    "Tiltás törölve": "Block deleted",
    "azonnal jóváhagyva": "approved immediately",
    "tömeges jóváhagyás": "bulk approval",
    "Felhasználónév: {u}": "Username: {u}",
}
