"""Generate the PWA icons in app/static/icons/ from the SVG below.

    docker run --rm -v "$PWD:/w" -w /w pdf-manager:test python scripts/make_icons.py
"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent.parent / "app/static/icons"

# Document with folded corner + magnifier, drawn in a 512x512 box (content kept inside the
# central 80% so the same drawing also works as a maskable icon).
CONTENT = """
  <path d="M168 96h128l96 96v200a24 24 0 0 1-24 24H168a24 24 0 0 1-24-24V120a24 24 0 0 1 24-24z" fill="#fff"/>
  <path d="M296 96v72a24 24 0 0 0 24 24h72z" fill="#f8b4b6"/>
  <rect x="184" y="224" width="144" height="18" rx="9" fill="#f3c2c3"/>
  <rect x="184" y="266" width="112" height="18" rx="9" fill="#f3c2c3"/>
  <rect x="184" y="308" width="80" height="18" rx="9" fill="#f3c2c3"/>
  <circle cx="318" cy="334" r="54" fill="#fff" stroke="#1c2026" stroke-width="22"/>
  <path d="M357 373l46 46" stroke="#1c2026" stroke-width="28" stroke-linecap="round"/>
"""


def svg(rounded: bool, scale: float = 1.0) -> str:
    bg = '<rect width="512" height="512" rx="112" fill="#e5484d"/>' if rounded \
        else '<rect width="512" height="512" fill="#e5484d"/>'
    off = 256 * (1 - scale)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">{bg}'
            f'<g transform="translate({off} {off}) scale({scale})">{CONTENT}</g></svg>')


def render(svg_text: str, size: int, path: Path):
    doc = pymupdf.open(stream=svg_text.encode(), filetype="svg")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(size / 512, size / 512), alpha=True)
    pix.save(path)
    print("wrote", path, pix.width, "x", pix.height)


OUT.mkdir(parents=True, exist_ok=True)
(OUT / "icon.svg").write_text(svg(rounded=True))
render(svg(rounded=True), 192, OUT / "icon-192.png")
render(svg(rounded=True), 512, OUT / "icon-512.png")
render(svg(rounded=False, scale=0.8), 512, OUT / "icon-maskable-512.png")
