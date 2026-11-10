// The Studio tab beside Sessions and Bots: a narrow rack of cartridge spines.
// It only browses; Enter or a click opens the full Studio page on that game.
// Same catalogue, model and pixel font as the page; plain DOM, disposable.
//
// Keyboard model (checked against the Hermes Desktop host source):
// - The list is a single-level role="tree" with a roving tab stop: the selected row is
//   the one focusable element (tabindex 0), arrows/Home/End move focus between rows,
//   Enter/Space open. NOT role="listbox": the host treats any [role=listbox|menu|dialog]
//   in the document as an open overlay (apps/desktop/src/lib/keybinds/combo.ts
//   OVERLAY_SURFACE, read with a bare document.querySelector) and then stands its own
//   keys down app-wide: type-to-focus, '/', soft Enter, Esc-to-stop and the Enter/Esc
//   approval keys. A tab that stays mounted in the sidebar must never do that.
// - A focused [role=treeitem] is a control the host already leaves Enter/Space to
//   (composer-focus-keys.ts ENTER_ACTIVATES), so the host's soft Enter / approval keys
//   do not fire on top of the rack.
// - Keys the host claimed first (its capture-phase keybinds set defaultPrevented) are
//   never handled a second time here.
import { normaliseCatalogue, VERDICTS } from './model.js'
import { pixelLabel } from './icons.js'

function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

export function rackRows(cat) {
  const rows = [{ id: '__new__', kind: 'new', title: 'New game', colour: '#ffd36b' }]
  const games = cat.games.slice().sort((a, b) => (a.sample === b.sample ? a.title.localeCompare(b.title) : a.sample ? 1 : -1))
  for (const g of games) rows.push({ id: g.id, kind: 'game', title: g.title, colour: g.style.colour, verdict: g.verification.playtest, sample: g.sample })
  return rows
}

// Pure key -> rack action mapping (exported for tests).
export function rackKey(e, sel, count) {
  if (e.defaultPrevented || e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return null
  const last = Math.max(0, count - 1)
  switch (e.key) {
    case 'ArrowDown': return { type: 'move', to: Math.min(last, sel + 1) }
    case 'ArrowUp': return { type: 'move', to: Math.max(0, sel - 1) }
    case 'Home': return { type: 'move', to: 0 }
    case 'End': return { type: 'move', to: last }
    case 'Enter':
    case ' ': return { type: 'open' }
    default: return null
  }
}

export async function bootRack(root, opts = {}) {
  const hostApi = opts.host || {}
  let disposed = false
  let raw = null
  let error = null
  try {
    raw = hostApi.loadCatalogue ? await hostApi.loadCatalogue() : opts.catalogue
  } catch (err) {
    error = String(err && err.message ? err.message : err)
  }
  if (disposed) return { dispose() {} }
  const cat = normaliseCatalogue(raw || { schema: 'hermes64.studio.catalogue/1', games: [], styles: [] })
  const rows = rackRows(cat)
  let sel = Math.min(rows.length - 1, rows.length > 1 ? 1 : 0)
  root.classList.add('h64s', 'h64s-rack')
  const count = cat.games.length
  root.innerHTML =
    '<div class="rack-head">' + pixelLabel(error ? 'SHELF UNREADABLE' : count + (count === 1 ? ' GAME' : ' GAMES'), 1.6) + '</div>' +
    '<ol class="rack-list" role="tree" aria-label="Hermes64 games">' + rows.map((r, i) =>
      '<li class="rack-row' + (r.kind === 'new' ? ' is-new' : '') + '" role="treeitem" tabindex="-1" aria-selected="false" data-i="' + i + '" aria-label="' + esc(r.title) + '">' +
      '<span class="spine" style="--c:' + r.colour + '"><span class="notch"></span></span>' +
      '<span class="name">' + esc(r.title) + '</span>' +
      (r.kind === 'new' ? '<span class="plus">+</span>'
        : (r.sample ? '<span class="tape">' + pixelLabel('SAMPLE', 1.2) + '</span>' : '') +
          '<span class="pip" data-verdict="' + r.verdict + '" title="' + esc(VERDICTS[r.verdict].words) + '"></span>') +
      '</li>').join('') + '</ol>' +
    '<button type="button" class="rack-open">' + pixelLabel('OPEN STUDIO', 1.6) + '</button>'
  const list = root.querySelector('.rack-list')
  const rowEl = i => list.querySelector('.rack-row[data-i="' + i + '"]')
  function paint() {
    list.querySelectorAll('.rack-row').forEach(n => {
      const on = Number(n.dataset.i) === sel
      n.classList.toggle('is-on', on)
      n.setAttribute('aria-selected', on ? 'true' : 'false')
      n.tabIndex = on ? 0 : -1
    })
  }
  function move(i, focus) {
    sel = Math.max(0, Math.min(rows.length - 1, i))
    paint()
    const n = rowEl(sel)
    if (!n) return
    if (focus) n.focus({ preventScroll: true })
    if ((focus || root.contains(document.activeElement)) && n.scrollIntoView) n.scrollIntoView({ block: 'nearest' })
  }
  function open(i) {
    const r = rows[i]
    if (r && hostApi.openStudio) hostApi.openStudio({ sel: r.id })
  }
  const onKey = ev => {
    // Enter/Space on the OPEN STUDIO button keep the button's own activation.
    if (!ev.target || !ev.target.closest || !ev.target.closest('.rack-row')) return
    const a = rackKey(ev, sel, rows.length)
    if (!a) return
    ev.preventDefault()
    if (a.type === 'move') move(a.to, true)
    else open(sel)
  }
  const onClick = ev => {
    const row = ev.target.closest('.rack-row')
    if (row) { move(Number(row.dataset.i), true); open(sel); return }
    if (ev.target.closest('.rack-open')) open(sel)
  }
  root.addEventListener('keydown', onKey)
  root.addEventListener('click', onClick)
  paint()
  return {
    rows,
    select(id) {
      const i = rows.findIndex(r => r.id === id)
      if (i >= 0 && i !== sel) move(i, false)
    },
    dispose() {
      if (disposed) return
      disposed = true
      root.removeEventListener('keydown', onKey)
      root.removeEventListener('click', onClick)
      root.innerHTML = ''
      root.classList.remove('h64s', 'h64s-rack')
    }
  }
}
