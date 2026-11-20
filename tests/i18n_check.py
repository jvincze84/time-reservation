"""Fordítás-ellenőrzés (statikus, konténer nélkül fut):

1. minden _("…") / N_("…") szövegnek van angol fordítása az app/i18n.py EN szótárában,
2. a {helyőrzők} a magyar és az angol változatban azonosak,
3. a sablonokban nincs _() nélküli, látható szöveg (heurisztika),
4. nincs fölösleges (sehol nem használt) kulcs az EN szótárban.

    python3 tests/i18n_check.py            # hibák listája, kilépési kód 1 hiba esetén
    python3 tests/i18n_check.py --missing  # csak a hiányzó kulcsok, Python-szótár formában
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))
import i18n  # noqa: E402  (függőség nélküli modul)

# _("…") / N_("…") / _('…') – Python és Jinja; a szövegben nem lehet ugyanolyan idézőjel
CALL_RE = re.compile(r"""(?<![\w.])N?_\(\s*(?:"([^"\\]*)"|'([^'\\]*)')""")
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
# Látható szöveget tartalmazó attribútumok, amelyeknek fordítottnak kell lenniük
ATTR_RE = re.compile(r'\b(placeholder|title|aria-label|data-confirm|alt)="([^"{]*[A-Za-zÁ-ű][^"]*)"')


def used_keys():
    keys = {}
    for path in [APP / "app.py", APP / "i18n.py", *sorted((APP / "templates").glob("*.html"))]:
        for m in CALL_RE.finditer(path.read_text(encoding="utf-8")):
            keys.setdefault(m.group(1) if m.group(1) is not None else m.group(2), path.name)
    return keys


def untranslated_template_text():
    """Sablonokban _() nélkül maradt szövegek keresése (heurisztika)."""
    problems = []
    for path in sorted((APP / "templates").glob("*.html")):
        src = path.read_text(encoding="utf-8")
        for m in ATTR_RE.finditer(src):
            problems.append(f"{path.name}: {m.group(1)}=\"{m.group(2)}\"")
        text = re.sub(r"\{#.*?#\}", " ", src, flags=re.S)
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S)
        text = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", text, flags=re.S)
        text = re.sub(r"<[^>]*>", " ", text, flags=re.S)
        for word in re.findall(r"[A-Za-zÁ-ű][A-Za-zÁ-ű'’\-]+", text):
            problems.append(f"{path.name}: fordítatlan szöveg: {word!r}")
    return problems


def main():
    keys = used_keys()
    en = i18n.EN
    missing = [k for k in keys if k not in en]
    if "--missing" in sys.argv:
        for k in missing:
            print(f"    {k!r}: '',")
        return
    errors = [f"hiányzó angol fordítás ({keys[k]}): {k!r}" for k in missing]
    for k, v in en.items():
        if set(PLACEHOLDER_RE.findall(k)) != set(PLACEHOLDER_RE.findall(v)):
            errors.append(f"eltérő helyőrzők: {k!r} -> {v!r}")
        if not v.strip():
            errors.append(f"üres fordítás: {k!r}")
    unused = [k for k in en if k not in keys]
    errors += [f"nem használt kulcs az EN szótárban: {k!r}" for k in unused]
    errors += untranslated_template_text()
    # Python szintaxis-ellenőrzés (az app.py-t nem importáljuk, mert Flask kellene hozzá)
    ast.parse((APP / "app.py").read_text(encoding="utf-8"))

    print(f"i18n: {len(keys)} fordítandó szöveg, {len(en)} angol fordítás")
    if errors:
        print("\n".join(f"  ✗ {e}" for e in errors))
        sys.exit(1)
    print("  ✓ minden szöveg le van fordítva")


if __name__ == "__main__":
    main()
