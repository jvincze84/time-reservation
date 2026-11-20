// Időrács: kijelölés kattintással / húzással (egér) és koppintással / hosszú nyomás + húzással (érintés)
(() => {
  const grid = document.getElementById('tgrid');
  if (!grid) return;

  const MIN = +grid.dataset.min || 0;
  const MAX = +grid.dataset.max || 0;
  const LONG_PRESS_MS = 300;
  const MOVE_TOLERANCE = 8;

  const selSheet = document.getElementById('selSheet');
  const infoSheet = document.getElementById('infoSheet');
  const $ = (id) => document.getElementById(id);

  let sel = null;          // { col, anchor, end } – cellaindexek egy oszlopon belül
  let dragging = false;
  let pressTimer = null;
  let touchStart = null;
  let lastTouch = 0;       // érintés után a böngésző "egér" eseményeket is küld – ezeket kiszűrjük

  const cellsOf = (col) => col.querySelectorAll('.cell');
  const cellFromPoint = (x, y) => {
    const el = document.elementFromPoint(x, y);
    return el && el.classList.contains('cell') ? el : null;
  };
  const isFree = (c) => c && c.dataset.s === 'free';
  // A szövegek a sablonból jönnek, az aktuális nyelven (window.I18N, lásd app.py: js_i18n)
  const T = window.I18N || {};
  const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const toMin = (s) => { const [h, m] = s.split(':'); return +h * 60 + +m; };
  const fmtDur = (m) => [Math.floor(m / 60) && `${Math.floor(m / 60)} ${T.h}`, m % 60 && `${m % 60} ${T.min}`].filter(Boolean).join(' ');

  // ---------- Kijelölés ----------
  function begin(cell) {
    sel = { col: cell.parentElement, anchor: +cell.dataset.i, end: +cell.dataset.i };
    render();
  }

  // A kijelölést a horgonytól a cél felé bővítjük, de csak összefüggő szabad cellákon át
  function extendTo(cell) {
    if (!sel || !cell || cell.parentElement !== sel.col) return;
    const cells = cellsOf(sel.col);
    const target = +cell.dataset.i;
    const dir = target >= sel.anchor ? 1 : -1;
    let i = sel.anchor;
    while (i !== target && isFree(cells[i + dir])) i += dir;
    if (i !== sel.end) { sel.end = i; render(); }
  }

  function clear() {
    sel = null;
    render();
  }

  function range() {
    const lo = Math.min(sel.anchor, sel.end), hi = Math.max(sel.anchor, sel.end);
    const cells = cellsOf(sel.col);
    return { lo, hi, start: cells[lo].dataset.a, end: cells[hi].dataset.b };
  }

  function render() {
    grid.querySelectorAll('.cell.sel').forEach((c) => c.classList.remove('sel', 'sel-first', 'sel-last'));
    if (!sel) { hide(selSheet); return; }
    const { lo, hi, start, end } = range();
    const cells = cellsOf(sel.col);
    for (let i = lo; i <= hi; i++) cells[i].classList.add('sel');
    cells[lo].classList.add('sel-first');
    cells[hi].classList.add('sel-last');
    cells[lo].dataset.label = `${start}–${end}`;

    const dur = toMin(end) - toMin(start);
    $('selTime').textContent = `${start}–${end}`;
    $('selDur').textContent = `(${fmtDur(dur)})`;
    $('selDay').textContent = sel.col.dataset.label;
    let warn = '';
    if (MIN && dur < MIN) warn = fill(T.minWarn, { d: fmtDur(MIN) });
    if (MAX && dur > MAX) warn = fill(T.maxWarn, { d: fmtDur(MAX) });
    $('selWarn').textContent = warn;
    $('selWarn').hidden = !warn;
    $('bookBtn').disabled = !!warn;
    $('bookBtn').textContent = fill(T.bookBtn, { t: `${start}–${end}` });
    for (const f of selSheet.querySelectorAll('form')) {
      f.elements.day.value = sel.col.dataset.day;
      f.elements.start.value = start;
      f.elements.end.value = end;
    }
    hide(infoSheet);
    show(selSheet);
  }

  // Koppintás / kattintás: ha van kijelölés ugyanabban az oszlopban, a cél celláig bővít,
  // a kijelölésen belüli koppintás újrakezdi (egyetlen cellás kijelölésnél törli).
  function tap(cell, extend = true) {
    if (!isFree(cell)) return;
    if (sel && sel.col === cell.parentElement) {
      const { lo, hi } = range();
      const i = +cell.dataset.i;
      if (extend && (i < lo || i > hi)) {
        if (lo !== hi) sel.anchor = i < lo ? hi : lo;  // a távolabbi végét tartjuk meg horgonynak
        return extendTo(cell);
      }
      if (lo === hi && i === lo) return clear();
    }
    begin(cell);
  }

  // ---------- Egér ----------
  grid.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || Date.now() - lastTouch < 800) return;
    const cell = e.target.closest('.cell');
    if (!isFree(cell)) return;
    e.preventDefault();
    if (e.shiftKey && sel && sel.col === cell.parentElement) {
      extendTo(cell);
    } else if (sel && sel.anchor === sel.end && sel.col === cell.parentElement && +cell.dataset.i === sel.anchor) {
      clear();
      return;
    } else {
      begin(cell);
    }
    dragging = true;
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging || Date.now() - lastTouch < 800) return;
    const cell = cellFromPoint(e.clientX, e.clientY);
    if (cell) extendTo(cell);
  });
  window.addEventListener('mouseup', () => { dragging = false; });

  // ---------- Érintés ----------
  grid.addEventListener('touchstart', (e) => {
    lastTouch = Date.now();
    if (e.touches.length !== 1) return cancelPress();
    const t = e.touches[0];
    const cell = e.target.closest('.cell');
    if (!isFree(cell)) return;
    touchStart = { x: t.clientX, y: t.clientY, cell };
    pressTimer = setTimeout(() => {
      pressTimer = null;
      dragging = true;
      begin(cell);
      if (navigator.vibrate) navigator.vibrate(15);
    }, LONG_PRESS_MS);
  }, { passive: true });

  // Nem passzív, hogy húzás közben megakadályozhassuk a görgetést
  grid.addEventListener('touchmove', (e) => {
    lastTouch = Date.now();
    const t = e.touches[0];
    if (dragging) {
      e.preventDefault();
      extendTo(cellFromPoint(t.clientX, t.clientY));
      autoScroll(t.clientY);
      return;
    }
    if (pressTimer && Math.hypot(t.clientX - touchStart.x, t.clientY - touchStart.y) > MOVE_TOLERANCE) {
      cancelPress();  // görgetés – nem kijelölés
    }
  }, { passive: false });

  grid.addEventListener('touchend', (e) => {
    lastTouch = Date.now();
    if (pressTimer) {           // rövid koppintás
      cancelPress();
      e.preventDefault();       // ne jöjjön utána szintetikus kattintás
      tap(touchStart.cell);
    } else if (dragging) {
      dragging = false;
      e.preventDefault();
    }
  });
  grid.addEventListener('touchcancel', () => { cancelPress(); dragging = false; });
  grid.addEventListener('contextmenu', (e) => { if (e.target.closest('.cell')) e.preventDefault(); });

  function cancelPress() {
    if (pressTimer) clearTimeout(pressTimer);
    pressTimer = null;
  }

  // Húzás közben a képernyő szélén automatikusan görget
  function autoScroll(y) {
    const edge = 60;
    const bottomLimit = window.innerHeight - edge - (document.querySelector('.bottomnav')?.offsetHeight || 0);
    if (y < edge + 60) window.scrollBy(0, -12);
    else if (y > bottomLimit) window.scrollBy(0, 12);
  }

  // ---------- Foglalás / tiltás részletei ----------
  grid.addEventListener('click', (e) => {
    const ov = e.target.closest('.ov');
    if (!ov) return;
    clear();
    const d = ov.dataset;
    const pill = $('infoPill');
    const setForm = (id, url) => { const f = $(id); f.hidden = !url; if (url) f.action = url; };
    if (d.kind === 'booking') {
      $('infoTitle').textContent = d.title;
      $('infoSub').textContent = `${d.day} · ${d.time}`;
      pill.textContent = d.statusLabel;
      pill.className = `pill pill-${d.status}`;
      pill.hidden = false;
      $('infoNote').textContent = d.note ? `${T.qOpen}${d.note}${T.qClose}` : '';
      setForm('fApprove', d.approve);
      setForm('fReject', d.reject);
      setForm('fCancel', d.cancel);
      setForm('fDelRule', '');
    } else {
      $('infoTitle').textContent = T.blocked;
      $('infoSub').textContent = d.text;
      pill.hidden = true;
      $('infoNote').textContent = d.reason;
      setForm('fApprove', ''); setForm('fReject', ''); setForm('fCancel', '');
      setForm('fDelRule', d.del);
      const btn = $('fDelRule').querySelector('button');
      btn.onclick = () => confirm(d.series ? T.delSeries : T.delOne);
    }
    show(infoSheet);
  });

  // ---------- Panelek ----------
  function show(s) { s.hidden = false; document.body.classList.add('has-sheet'); }
  function hide(s) {
    s.hidden = true;
    if (selSheet.hidden && infoSheet.hidden) document.body.classList.remove('has-sheet');
  }
  document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => {
    if (b.closest('#selSheet')) clear(); else hide(infoSheet);
  }));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { clear(); hide(infoSheet); } });

  // A hét nézet fejléce a felső sáv alá ragad – ehhez kell a sáv valós magassága
  const topbar = document.querySelector('.topbar');
  const setTopbarH = () => topbar && document.documentElement.style.setProperty('--topbar-h', `${topbar.offsetHeight}px`);
  setTopbarH();
  window.addEventListener('resize', setTopbarH);

  // Mobilon csak a releváns tipp látszik
  if (window.matchMedia('(pointer: coarse)').matches) document.body.classList.add('touch');

  // Nap nézetben a mai napon görgessünk az aktuális időhöz közel
  const firstFree = grid.querySelector('.tg-col.is-today .cell.c-free');
  if (firstFree && grid.classList.contains('is-day')) {
    const y = firstFree.getBoundingClientRect().top + window.scrollY - 160;
    if (y > 200) window.scrollTo({ top: y });
  }
})();
