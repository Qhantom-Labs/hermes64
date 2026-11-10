// Hermes64 Studio shell: plain DOM, no framework, no build step.
// Runs the prototype page and, unchanged, the desktop plugin page: everything
// that differs between the two arrives through `opts.host` (catalogue, images,
// chat hand-off, play, reveal, native launch, eject). Without a host it falls
// back to the bundled sample. studio/tools/sync_shared.py copies this file and
// the pure modules (model/state/cartridge/covers/pixelfont/icons/motion/input/
// sound) into desktop/plugin.js and dist/studio.bundle.js.
import { normaliseCatalogue, FILTERS, VERDICTS, verificationRows, verificationDots, moduleBadge, counterText, STYLE_STATUS_WORDS, errorSentence } from './model.js'
import { initialState, reduce, shelfItems, selectedIndex, detailMenu, newGameStyles, NAV } from './state.js'
import { cartSVG } from './cartridge.js'
import { coverCanvas, styleRecipe } from './covers.js'
import { navIconSVG, wordmarkSVG, pixelLabel, counterFit, glyphHTML, HINTS } from './icons.js'
import { Tween, EASE } from './motion.js'
import { keyAction, PadReader } from './input.js'
import { SoundBank } from './sound.js'
import { TILE, TILE_URL } from './pattern.js'

const SAMPLE_URL = 'catalogue.sample.json'

function qs() {
  const out = {}
  const raw = (location.hash || '').replace(/^#/, '') + '&' + (location.search || '').replace(/^\?/, '')
  for (const part of raw.split('&')) {
    if (!part) continue
    const i = part.indexOf('=')
    const k = decodeURIComponent(i < 0 ? part : part.slice(0, i))
    out[k] = i < 0 ? '1' : decodeURIComponent(part.slice(i + 1))
  }
  return out
}

function el(tag, cls, html) {
  const n = document.createElement(tag)
  if (cls) n.className = cls
  if (html != null) n.innerHTML = html
  return n
}

// The room behind the shelf: an original, bright illustrated backdrop. A pale sky,
// a huge soft periwinkle workbench, a warm sunny block and a giant faint box card
// leaning in the corner. Everything is soft and low-contrast so the cards carry the
// colour. Over it drifts a pattern of mini Qhantom Labs marks (patternHTML).
function backdropSVG() {
  const card = (x, y, w, h, r, fill, op) => '<g transform="rotate(' + r + ' ' + (x + w / 2) + ' ' + (y + h / 2) + ')" opacity="' + op + '">' +
    '<rect x="' + (x + 14) + '" y="' + (y + 14) + '" width="' + w + '" height="' + h + '" rx="18" fill="#9fb8e6"/>' +
    '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="18" fill="' + fill + '"/>' +
    '<rect x="' + (x + 16) + '" y="' + (y + 30) + '" width="' + (w - 32) + '" height="' + (h * 0.56) + '" rx="8" fill="#cfe0fb"/>' +
    [0, 1, 2, 3].map(i => '<circle cx="' + (x + 34 + i * 30) + '" cy="' + (y + h - 36) + '" r="10" fill="none" stroke="#c4d4ef" stroke-width="5"/>').join('') + '</g>'
  return '<svg class="h64s-bg" viewBox="0 0 1280 720" preserveAspectRatio="xMidYMid slice" aria-hidden="true">' +
    '<defs><linearGradient id="h64s-bg-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.5" stop-color="#eef5ff"/><stop offset="1" stop-color="#dce9fc"/></linearGradient>' +
    '<linearGradient id="h64s-bg-bench" x1="0" y1="0" x2="0.6" y2="1"><stop offset="0" stop-color="#8cb6fa"/><stop offset="1" stop-color="#5a8ff2"/></linearGradient>' +
    '<linearGradient id="h64s-bg-sun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffeea0"/><stop offset="1" stop-color="#ffcc47"/></linearGradient></defs>' +
    '<rect width="1280" height="720" fill="url(#h64s-bg-sky)"/>' +
    card(1010, -60, 250, 290, 9, '#f4f8ff', 0.85) +
    '<path d="M-60 300Q-60 214 30 208L820 176Q930 172 948 280L1000 760L-60 760Z" fill="url(#h64s-bg-bench)" opacity="0.7"/>' +
    '<path d="M60 262Q60 236 90 234L760 212Q800 211 806 240L812 300Q814 322 790 324L90 344Q60 345 60 320Z" fill="#c7dcfb" opacity="0.7"/>' +
    '<path d="M960 760L990 380Q1004 300 1090 296L1320 290L1320 760Z" fill="url(#h64s-bg-sun)" opacity="0.72"/>' +
    '<g opacity="0.55"><circle cx="1160" cy="196" r="64" fill="#fff4c4"/><circle cx="1160" cy="196" r="44" fill="#ffe27a"/></g>' +
    '<g fill="#ffffff" opacity="0.9"><path d="M1180 470l6 14 14 6-14 6-6 14-6-14-14-6 14-6z"/><path d="M118 150l4 10 10 4-10 4-4 10-4-10-10-4 10-4z"/><path d="M560 120l3 8 8 3-8 3-3 8-3-8-8-3 8-3z"/></g>' +
    '</svg>'
}

// The pattern: a tile of mini Qhantom Labs marks (studio/tools/make_pattern.py draws it pixel by
// pixel from the traced mark) repeated over the whole backdrop at one CSS pixel per tile pixel,
// so it is never resampled. It drifts slowly up and to the left along the tile's 45-degree
// lattice in whole device pixels (see setDrift in boot), paused for reduced motion and in
// capture modes.
function patternHTML() {
  return '<div class="h64s-pattern-wrap" aria-hidden="true"><div class="h64s-pattern" data-variant="' + TILE.variant + '" style="background-image:url(' + TILE_URL + ');background-size:' + TILE.tileW + 'px ' + TILE.tileH + 'px"></div></div>'
}
const DRIFT_SPEED = 6 // CSS px per second along each axis

// Scale test only (#catalogue=scale&count=300): clones of the SAMPLE rows, renamed and
// re-seeded, so the shelf can be driven at library sizes. Never used by the plugin.
function scaleFixture(raw, count) {
  const base = raw.games.filter(g => g.sample)
  const words = ['Amber', 'Basalt', 'Cobalt', 'Dune', 'Ember', 'Fern', 'Glacier', 'Harbor', 'Iris', 'Juniper', 'Kelp', 'Lumen', 'Moss', 'Nimbus', 'Opal', 'Pine', 'Quartz', 'Reef', 'Slate', 'Tide']
  const games = []
  for (let i = 0; i < count; i++) {
    const g = JSON.parse(JSON.stringify(base[i % base.length]))
    g.id = 'scale_' + String(i).padStart(4, '0')
    g.title = words[i % words.length] + ' ' + words[Math.floor(i / words.length) % words.length] + ' ' + (i + 1)
    if (g.cover && g.cover.recipe) g.cover.recipe.seed = g.id
    delete g.shots
    games.push(g)
  }
  return Object.assign({}, raw, { games })
}

// Card titles are SVG text in a system font; squeeze any line that measures wider
// than the art once the card is in the document.
function fitCardTitles(scope) {
  scope.querySelectorAll('svg.cart-svg:not([data-fit])').forEach(svg => {
    svg.setAttribute('data-fit', '1')
    svg.querySelectorAll('text[data-maxw]').forEach(t => {
      let w = 0
      try { w = t.getComputedTextLength() } catch (err) { w = 0 }
      const max = Number(t.getAttribute('data-maxw'))
      if (w > max) { t.setAttribute('textLength', String(max)); t.setAttribute('lengthAdjust', 'spacingAndGlyphs') }
    })
  })
}

export async function boot(root, opts = {}) {
  const hostApi = opts.host || {}
  const params = Object.assign(opts.useLocation === false ? {} : qs(), opts.params || {})
  const disposers = []
  let disposed = false
  let rafId = 0
  // clock=manual freezes time for frame-exact filmstrips: tests call __h64.advance(ms).
  const manual = params.clock === 'manual'
  let manualNow = 10000
  const clock = () => (manual ? manualNow : performance.now())
  const errors = []
  const debug = { ready: false, errors, handoffs: [], reveals: [], plays: [], frames: 0, actions: 0 }
  if (opts.debug !== false) window.__h64 = debug

  // ---------------- catalogue ----------------
  let raw = null
  let loadError = null
  try {
    if (params.catalogue === 'empty') raw = { schema: 'hermes64.studio.catalogue/1', source: 'sample', games: [], styles: [] }
    else if (params.catalogue === 'broken') throw new Error('The catalogue file could not be read (sample error state)')
    else if (hostApi.loadCatalogue) raw = await hostApi.loadCatalogue()
    else if (opts.catalogue) raw = opts.catalogue
    else if (window.H64_SAMPLE_CATALOGUE) raw = window.H64_SAMPLE_CATALOGUE
    else {
      const res = await fetch(SAMPLE_URL, { cache: 'no-store' })
      if (!res.ok) throw new Error('HTTP ' + res.status)
      raw = await res.json()
    }
  } catch (err) {
    loadError = String(err && err.message ? err.message : err)
  }
  if (raw && params.catalogue === 'scale') raw = scaleFixture(raw, Math.max(0, Math.min(2000, Number(params.count) || 300)))
  const bootT0 = performance.now()
  const cat = normaliseCatalogue(raw || { schema: 'hermes64.studio.catalogue/1', games: [], styles: [] })
  if (raw && cat.problems.length) errors.push.apply(errors, cat.problems.map(p => p.code))

  // ---------------- art ----------------
  // Captured covers may arrive asynchronously from the host (data URLs from the
  // plugin backend); until then a procedural stand-in in the game's palette shows.
  // Art is painted lazily: a cover when its card first comes near the screen,
  // back-of-box shots when the detail card opens. 300 games cost what 14 do.
  const art = {}
  const artIsCapture = {}
  const shots = {}
  const pendingArt = []
  const gameById = {}
  for (const g of cat.games) {
    gameById[g.id] = g
    if (g.cover.kind !== 'procedural' && g.cover.src && hostApi.image) pendingArt.push({ key: g.id, src: g.cover.src })
    if (hostApi.image) g.shots.forEach((sh, i) => { if (sh.src) pendingArt.push({ key: g.id, shot: i, src: sh.src }) })
  }
  function recipeFor(g) {
    return g.cover.recipe || { seed: g.id, sky: [g.style.palette[0] || '#5a6fb8', g.style.palette[3] || '#ffd9a8'], layers: [{ kind: 'mountains', colour: g.style.colour, base: 0.62, height: 0.3 }], ground: g.style.palette[1] || '#6c8fd0' }
  }
  let paintBudget = Infinity // the frame loop allows two new covers per frame
  function artFor(key, deferrable) {
    if (art[key]) return art[key]
    if (deferrable && paintBudget <= 0) return null
    paintBudget--
    if (key.startsWith('style:')) {
      const st = cat.styles.find(x => 'style:' + x.id === key)
      art[key] = st ? coverCanvas(document, styleRecipe(st)).toDataURL('image/png') : ''
      return art[key]
    }
    const g = gameById[key]
    if (!g) return ''
    if (g.cover.kind !== 'procedural' && g.cover.src && !hostApi.image) {
      art[key] = g.cover.src
      artIsCapture[key] = true
    } else art[key] = coverCanvas(document, recipeFor(g)).toDataURL('image/png')
    return art[key]
  }
  function shotsFor(g) {
    if (shots[g.id]) return shots[g.id]
    const recipe = recipeFor(g)
    shots[g.id] = g.shots.length
      ? g.shots.map((sh, i) => (sh.src && !hostApi.image ? sh.src : coverCanvas(document, sh.recipe || recipe, 1 + (i % 3)).toDataURL('image/png')))
      : g.cover.recipe ? [1, 2, 3].map(v => coverCanvas(document, g.cover.recipe, v).toDataURL('image/png')) : []
    return shots[g.id]
  }

  const cartCache = {}
  function artReady(item) {
    if (item.type === 'new') return true
    const key = item.type === 'style' ? 'style:' + item.id : item.id
    return !!art[key] || artFor(key, true) !== null
  }
  function gameSpec(g, withArt) {
    return {
      uid: (withArt ? 'g-' : 'p-') + g.id,
      kind: withArt ? 'game' : 'pending',
      shell: g.style.colour,
      title: g.title,
      coverHref: withArt ? artFor(g.id) : null,
      capture: withArt && !!artIsCapture[g.id],
      // only once the real box art is painted (artIsCapture): the procedural stand-in keeps the cartridge's title
      boxArt: withArt && g.cover.kind === 'box' && !!artIsCapture[g.id],
      focus: g.cover.focus,
      srcW: g.cover.width,
      srcH: g.cover.height,
      grade: g.cover.grade,
      titlePos: g.cover.title,
      dots: verificationDots(g),
      badge: moduleBadge(g),
      tape: g.sample ? 'SAMPLE' : null,
      ariaLabel: g.title
    }
  }
  function cartFor(item) {
    const key = item.type + ':' + item.id
    if (cartCache[key]) return cartCache[key]
    if (!artReady(item)) {
      // Plain card until the cover is painted on a later frame (never cached).
      if (item.type === 'style') return cartSVG({ uid: 'p-' + item.id, kind: 'pending', shell: item.style.colour, title: item.style.label, palette: item.style.palette, ariaLabel: item.style.label })
      return cartSVG(gameSpec(item.game, false))
    }
    let svg
    if (item.type === 'new' && loadError) svg = cartSVG({ uid: 'err', kind: 'error', title: 'SHELF UNREADABLE', ariaLabel: 'The shelf could not be read' })
    else if (item.type === 'new') svg = cartSVG({ uid: 'new', kind: 'new', title: 'NEW GAME', ariaLabel: 'New game' })
    else if (item.type === 'style') {
      const s = item.style
      const draft = s.status === 'draft_awaiting_approval'
      svg = cartSVG({ uid: 'st-' + s.id, kind: 'style', shell: s.colour, title: s.label, coverHref: artFor('style:' + s.id), palette: s.palette, badgeText: draft ? 'DRAFT' : s.status === 'approved' ? 'OK' : s.status === 'in_use' ? 'USED' : 'DATA', badgeFill: draft ? null : s.status === 'approved' ? '#8fe39a' : '#e4e8f0', tape: s.sample ? 'SAMPLE' : null, ariaLabel: s.label + ' style' })
    } else svg = cartSVG(gameSpec(item.game, true))
    cartCache[key] = svg
    return svg
  }

  // ---------------- skeleton ----------------
  root.classList.add('h64s')
  root.tabIndex = 0
  root.setAttribute('role', 'application')
  root.setAttribute('aria-roledescription', 'game catalogue')
  root.setAttribute('aria-label', 'Hermes64 Studio')
  root.innerHTML = ''
  const backdrop = el('div', 'h64s-backdrop', backdropSVG() + patternHTML())
  const top = el('header', 'h64s-top',
    '<div class="h64s-brand">' + wordmarkSVG() + '</div>' +
    '<nav class="h64s-bar pxf" role="toolbar" aria-label="Studio menu">' +
    NAV.map((n, i) => '<button type="button" class="h64s-nav" data-nav="' + n.id + '" data-index="' + i + '" aria-label="' + n.label + '">' + navIconSVG(n.id) + '</button>').join('') +
    '</nav><div class="h64s-tip pxf"><svg class="tip-point" viewBox="0 0 22 12" aria-hidden="true"><path d="M0 12L11 0L22 12Z" fill="#1b1d2c"/><path d="M4 12L11 4.5L18 12Z" fill="#ffffff"/></svg><span class="tip-text"></span></div>' +
    '<div class="h64s-counter pxf" aria-hidden="true"><span class="counter-head"></span><span class="counter-pos"></span></div>')
  const title = el('div', 'h64s-title pxf', '<span class="title-find">' + pixelLabel('FIND', 2) + '</span><span class="title-miss">' + pixelLabel('NO MATCH', 2) + '</span><span class="title-text"></span><span class="title-tag is-hidden">' + pixelLabel('SAMPLE', 2) + '</span><input class="title-input" type="text" spellcheck="false" aria-label="Jump to a game by name" maxlength="40">')
  const stage = el('main', 'h64s-stage')
  const shelfEl = el('div', 'h64s-shelf')
  stage.appendChild(shelfEl)
  const strip = el('div', 'h64s-strip', '<div class="thumbs"></div><div class="caret"></div>')
  const hints = el('footer', 'h64s-hints')
  const notice = el('div', 'h64s-notice pxf')
  notice.setAttribute('aria-live', 'polite')
  const panel = el('section', 'h64s-panel pxf is-detail')
  const ngPanel = el('section', 'h64s-panel pxf is-newgame')
  const help = el('section', 'h64s-help pxf')
  help.setAttribute('aria-label', 'Controls')
  const errorEl = el('div', 'h64s-error')
  const play = el('div', 'h64s-play', '<div class="screen"><div class="content"></div><div class="crt"></div></div><div class="eject"></div>')
  const slotbay = el('div', 'h64s-slotbay')
  const live = el('div', 'sr')
  live.setAttribute('aria-live', 'polite')
  for (const n of [backdrop, stage, top, title, strip, panel, ngPanel, errorEl, hints, help, notice, slotbay, play, live]) root.appendChild(n)

  // ---------------- state ----------------
  const reduced = params.motion === 'reduce' || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  root.dataset.motion = reduced ? 'reduce' : 'full'
  let state = initialState({ filter: params.filter, sel: params.sel, shelf: params.shelf, input: params.input })
  if (params.styleSel) state.sel.styles = params.styleSel
  const caps = Object.assign({ reveal: true }, hostApi.caps || {})
  const sound = new SoundBank(opts.audioBase || '../../audio/', params.sound === 'on', hostApi.soundUrl || null)
  let frameUrl = null
  let stripDirty = false
  const pad = new PadReader()
  const scroll = new Tween(0)
  let view0 = 0
  let enterAt = 0
  let enterDir = 1
  let bumpAt = 0
  let selAt = 0
  let playPhase = null
  let playStart = 0
  let lastItemsKey = ''
  let slots = {}
  let layout = { u: 1, narrow: false, fy: 508, pitch: 256 }
  let announceTimer = 0
  let noticeRef = null
  let noticeAt = 0
  let jumpScroll = false
  let tipHover = null

  function items() {
    return shelfItems(cat, state)
  }

  // ---------------- layout ----------------
  // Composed on a 1280x720 stage (600x760 when narrow) and scaled by one unit, --u.
  function measure() {
    const W = root.clientWidth || window.innerWidth
    const H = root.clientHeight || window.innerHeight
    const narrow = W < 760 || W / H < 1.05
    let u, ox, oy, fy
    if (narrow) {
      u = Math.max(0.5, Math.min(1.6, W / 600, H / 760))
      ox = (W - 600 * u) / 2
      oy = Math.max(0, (H - 760 * u) / 2)
      fy = oy + 530 * u
    } else {
      u = Math.max(0.55, Math.min(2.2, W / 1280, H / 720))
      ox = (W - 1280 * u) / 2
      oy = Math.max(0, (H - 720 * u) / 2)
      fy = oy + 508 * u
    }
    layout = { u, ox, oy, fy, W, H, narrow, pitch: 256 * u }
    root.dataset.layout = narrow ? 'narrow' : 'wide'
    root.style.setProperty('--u', u + 'px')
    root.style.setProperty('--ox', ox + 'px')
    root.style.setProperty('--oy', oy + 'px')
    root.style.setProperty('--fy', fy + 'px')
    // the pattern layer is one drift period larger than the room (studio.css)
    root.style.setProperty('--drift-d', TILE.period + 'px')
  }

  // ---------------- backdrop drift ----------------
  // The pattern drifts up and to the left along its 45-degree lattice: one lattice period per
  // loop, one device pixel per step on both axes (steps() easing, so the layer is never resampled
  // between pixels: no shimmer). A Web Animation with a steps() easing only wakes the main thread
  // when the step changes (12 times a second at 2x); on the real host a CSS animation, even a
  // trivial one, recalculated style every frame. It stands still for reduced motion (also when
  // that setting changes) and in capture modes: a manual clock (frame-exact filmstrips) or
  // drift=off (screenshots).
  let driftAnim = null
  let driftDpr = 0
  const motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
  function setDrift() {
    const want = !disposed && !manual && params.drift !== 'off' && params.motion !== 'reduce' && !(motionQuery && motionQuery.matches)
    const layer = backdrop.querySelector('.h64s-pattern')
    const dpr = Math.max(1, Math.round(window.devicePixelRatio || 1))
    if (driftAnim && (!want || dpr !== driftDpr)) { driftAnim.cancel(); driftAnim = null }
    root.dataset.drift = want && layer && layer.animate ? 'on' : 'off'
    if (!want || driftAnim || !layer || !layer.animate) return
    const d = TILE.period
    driftDpr = dpr
    driftAnim = layer.animate([{ transform: 'translate3d(0px, 0px, 0px)' }, { transform: 'translate3d(' + -d + 'px, ' + -d + 'px, 0px)' }],
      { duration: (d / DRIFT_SPEED) * 1000, iterations: Infinity, easing: 'steps(' + d * dpr + ')' })
  }

  // ---------------- rendering ----------------
  // Only cards near the visible page exist in the DOM (about a dozen at any size);
  // ensureSlots() creates and drops them as the row scrolls.
  let slotList = []
  let slotRange = ''
  function makeSlot(it) {
    const s = el('div', 'h64s-slot', '<div class="cart">' + cartFor(it) + '</div>')
    if (!cartCache[it.type + ':' + it.id]) s.dataset.pending = '1'
    s.dataset.id = it.id
    s.addEventListener('click', ev => {
      ev.stopPropagation()
      dispatch({ type: 'select_id', id: it.id })
    })
    return s
  }
  function ensureSlots(center, force) {
    const n = slotList.length
    const radius = Math.ceil((layout.W || 1280) / (layout.pitch || 256) / 2) + 3
    const lo = Math.max(0, Math.floor(center) - radius)
    const hi = Math.min(n - 1, Math.ceil(center) + radius)
    const key = state.shelf + ':' + lo + ':' + hi
    if (key === slotRange && !force) return
    slotRange = key
    const keep = {}
    for (let i = lo; i <= hi; i++) {
      const it = slotList[i]
      const k = it.id + '@' + state.shelf
      const s = slots[k] || makeSlot(it)
      s.dataset.index = i
      keep[k] = s
      if (s.parentNode !== shelfEl) { shelfEl.appendChild(s); fitCardTitles(s) }
    }
    for (const k of Object.keys(slots)) if (!keep[k]) slots[k].remove()
    slots = keep
  }

  function layoutCount(list) {
    return state.shelf === 'games' && list.length === 1 && !loadError ? 5 : list.length
  }
  function pageFor(idx, n, prev) {
    // Four whole cards per page with half cards at the edges; the highlight moves
    // within the page and the row only slides when it would leave it.
    if (n < 4) return -(4 - n) / 2
    let v = Math.round(prev)
    if (v < 0) v = 0
    if (idx > v + 3) v = idx - 3
    if (idx < v) v = idx
    return Math.max(0, Math.min(v, n - 4))
  }

  function buildShelf(now) {
    const list = items()
    const key = state.shelf + '|' + state.filter + '|' + list.map(i => i.id).join(',')
    if (key === lastItemsKey) return
    lastItemsKey = key
    slotList = list
    for (const k of Object.keys(slots)) if (!list.some(it => it.id + '@' + state.shelf === k)) { slots[k].remove(); delete slots[k] }
    view0 = pageFor(selectedIndex(list, state), layoutCount(list), view0)
    ensureSlots(selectedIndex(list, state), true)
    // Empty shelf: ghost cards show a shelf waiting to be filled.
    shelfEl.querySelectorAll('.is-ghost-slot').forEach(n => n.remove())
    if (state.shelf === 'games' && list.length === 1 && !loadError) {
      for (let g = 1; g <= 4; g++) {
        const ghost = el('div', 'h64s-slot is-ghost-slot', '<div class="cart">' + cartSVG({ kind: 'ghost' }) + '</div>')
        ghost.dataset.index = g
        ghost.style.pointerEvents = 'none'
        shelfEl.appendChild(ghost)
      }
    }
    enterAt = now
    stripWindow = -1
    renderStrip()
    measure()
  }

  let stripWindow = -1
  function renderStrip() {
    const list = items()
    const idx = selectedIndex(list, state)
    const thumbs = strip.querySelector('.thumbs')
    const max = layout.narrow ? 16 : 38
    let a = 0
    if (list.length > max) a = Math.max(0, Math.min(list.length - max, idx - Math.floor(max / 2)))
    if (a === stripWindow && !stripDirty) return
    stripWindow = a
    strip.classList.toggle('is-empty', list.length <= 1)
    let html = ''
    let prevGroup = null
    const b = Math.min(list.length, a + max)
    for (let i = a; i < b; i++) {
      const it = list[i]
      const gap = it.group && prevGroup !== null && it.group !== prevGroup ? ' is-gap' : ''
      prevGroup = it.group
      if (it.type === 'new') { html += '<div class="thumb is-new" data-index="' + i + '"></div>'; continue }
      const key = it.type === 'style' ? 'style:' + it.id : it.id
      const src = art[key] || artFor(key, true)
      const colour = it.type === 'style' ? it.style.colour : it.game.style.colour
      if (!src) stripDirty = true
      html += '<div class="thumb' + gap + (src ? '' : ' is-plain') + '" data-index="' + i + '" style="' + (src ? 'background-image:url(' + JSON.stringify(src).slice(1, -1) + ')' : 'background:' + colour) + '"></div>'
    }
    if (list.length <= 1 && state.shelf === 'games') for (let g = 0; g < 5; g++) html += '<div class="thumb"></div>'
    thumbs.innerHTML = html
  }

  function setHints(names) {
    hints.innerHTML = names.map((n, i) => {
      const h = HINTS[n]
      return '<div class="h64s-hint' + (i >= 2 ? ' is-extra' : '') + '">' + glyphHTML(h, state.input) + '<span class="hint-label">' + escapeHtml(h.label) + '</span></div>'
    }).join('')
  }

  function renderHelp() {
    const row = (h, words) => '<div class="help-row">' + glyphHTML(HINTS[h], state.input) + '<span>' + words + '</span></div>'
    help.innerHTML = '<div class="help-title">' + pixelLabel('CONTROLS', 2.4) + '</div><div class="help-grid">' +
      row('browse', 'Browse the shelf') + row('open', 'Open a game') + row('menu', 'Menu: Games, Styles, Filters, Help') + row('back', 'Back') +
      row('prev', 'Previous filter') + row('next', 'Next filter') + row('find', 'Find a game by name') + row('page', 'Page through a long shelf') +
      '</div><div class="help-foot">' + pixelLabel('M · SOUND ON/OFF', 1.8) + '</div>'
  }

  let lastTitle = ''
  let lastSelected = null
  let lastSelKey = ''
  function renderChrome() {
    const list = items()
    const idx = selectedIndex(list, state)
    const it = list[idx]
    const selKey = state.shelf + ':' + (it ? it.id : '')
    if (selKey !== lastSelKey) { lastSelKey = selKey; selAt = clock() }
    if (it && it.id !== lastSelected && state.shelf === 'games') {
      lastSelected = it.id
      if (hostApi.onSelect) { try { hostApi.onSelect(it.id) } catch (err) { errors.push(String(err)) } }
    }
    root.dataset.view = state.view
    root.dataset.shelf = state.shelf
    root.dataset.input = state.input
    root.classList.toggle('is-jump', !!state.jump)
    root.classList.toggle('is-miss', !!(state.jump && state.jump.miss))
    root.classList.toggle('is-error', !!loadError)
    root.classList.toggle('is-bar', state.bar != null)
    root.classList.toggle('is-help', !!state.help)

    // icon bar: the cursor when it is in the bar, otherwise the current shelf
    // lit icon: the pointer's, else the bar cursor, else where you are (an active filter lights Filters)
    const lit = tipHover != null ? tipHover : state.bar != null ? state.bar : state.shelf === 'styles' ? 1 : state.filter !== 'all' ? 2 : 0
    top.querySelectorAll('.h64s-nav').forEach(b => {
      const i = Number(b.dataset.index)
      b.classList.toggle('is-lit', i === lit)
      b.classList.toggle('is-cursor', state.bar === i)
      b.setAttribute('aria-pressed', NAV[i].id === (state.shelf === 'styles' ? 'styles' : 'games') ? 'true' : 'false')
    })
    const f = FILTERS.find(x => x.id === state.filter)
    const tipText = NAV[lit].id === 'filters' ? 'Filters: ' + f.label.charAt(0) + f.label.slice(1).toLowerCase() : NAV[lit].label
    const tip = top.querySelector('.h64s-tip')
    tip.querySelector('.tip-text').textContent = tipText
    tip.style.setProperty('--tip-x', String(lit))

    // counter
    const c = state.shelf === 'styles' ? counterText('STYLES', list.map(x => x), idx) : counterText(f.label, list, idx)
    // a grouped filter shows the group you are in ("UNTESTED 11/14"); long names step down a size.
    // The plate grows left up to its max-width (studio.css), so the words always fit inside it:
    // room = max-width minus padding, in stage units.
    const head = it && it.group && state.shelf === 'games' ? it.group : c.head.split(' · ')[0]
    const fit = layout.narrow ? counterFit(head, c.pos, 288 - 40, 8, head.length + c.pos.length > 14 ? 2 : 2.4)
      : counterFit(head, c.pos, 408 - 52, 14, head.length + c.pos.length > 14 ? 2 : 2.4)
    top.querySelector('.counter-head').innerHTML = pixelLabel(fit.head, fit.size)
    top.querySelector('.counter-pos').innerHTML = pixelLabel(c.pos, fit.size)

    // title
    let text = 'New Game'
    let tag = false
    if (loadError) text = 'Can\'t read the shelf'
    else if (it && it.type === 'game') { text = it.game.title; tag = it.game.sample }
    else if (it && it.type === 'style') { text = it.style.label; tag = it.style.sample }
    const tt = title.querySelector('.title-text')
    if (text !== lastTitle) {
      tt.textContent = text
      tt.classList.remove('is-swap')
      void tt.offsetWidth
      tt.classList.add('is-swap')
      lastTitle = text
    }
    title.querySelector('.title-tag').classList.toggle('is-hidden', !tag)
    const input = title.querySelector('.title-input')
    if (state.jump && document.activeElement !== input) {
      input.value = state.jump.text
      input.focus()
    }
    if (!state.jump && document.activeElement === input) root.focus()

    // strip window, highlight and pointer
    renderStrip()
    strip.querySelectorAll('.thumb').forEach(n => n.classList.toggle('is-on', Number(n.dataset.index) === idx))
    const on = strip.querySelector('.thumb.is-on')
    const caret = strip.querySelector('.caret')
    if (on) {
      caret.style.display = 'block'
      caret.style.left = (on.offsetLeft + on.offsetWidth / 2) + 'px'
    } else caret.style.display = 'none'

    // hints
    if (state.help) setHints(['close'])
    else if (state.jump) setHints(['type', 'open', 'cancel'])
    else if (state.view === 'detail') setHints(state.confirm ? ['select', 'cancel'] : ['choose', 'select', 'back', 'browse'])
    else if (state.view === 'newgame') setHints(['hand', 'cancel', 'style'])
    else if (state.view === 'play') setHints(['eject'])
    else if (loadError) setHints(['retry'])
    else if (state.bar != null) setHints(['across', 'select', 'back'])
    else if (state.shelf === 'styles') setHints(['open', 'menu', 'back'])
    else if (list.length <= 1) setHints(['open', 'menu'])
    else if (list.length > 40) setHints(['open', 'menu', 'prev', 'next', state.input === 'pad' ? 'page' : 'find'])
    else setHints(['open', 'menu', 'prev', 'next'])
    if (state.help) renderHelp()

    // notice
    if (state.notice && state.notice.text) {
      notice.innerHTML = pixelLabel(state.notice.text.toUpperCase().slice(0, 48), 2)
      notice.dataset.tone = state.notice.tone || 'good'
      notice.classList.add('is-on')
    } else notice.classList.remove('is-on')

    errorEl.textContent = loadError ? errorSentence(loadError) : ''
    if (state.view === 'detail') renderDetail(it)
    if (state.view === 'newgame') renderNewGame()
    else liveNewCart(false)

    // announce
    clearTimeout(announceTimer)
    announceTimer = setTimeout(() => {
      if (!it) return
      if (state.bar != null) live.textContent = NAV[state.bar].label + ' menu.'
      else if (it.type === 'new') live.textContent = 'New game card. Press Enter to start a game with Hermes.'
      else if (it.type === 'style') live.textContent = it.style.label + ' style. ' + (STYLE_STATUS_WORDS[it.style.status] || '')
      else live.textContent = it.game.title + '. ' + c.pos.replace('/', ' of ') + '. Bot playtest ' + VERDICTS[it.game.verification.playtest].label.toLowerCase() + '. Story proof ' + it.game.verification.proof.replace('_', ' ') + '.' + (it.game.verification.human === 'played' ? ' Played by a person.' : ' Not yet played by a person.') + (it.game.sample ? ' Sample entry.' : '')
    }, 220)
  }

  function renderDetail(it) {
    if (!it || it.type === 'new') return
    const menu = detailMenu(it, caps)
    if (it.type === 'style') {
      const s = it.style
      panel.innerHTML = '<p class="premise">' + escapeHtml(STYLE_STATUS_WORDS[s.status] || '') + (s.note ? '. ' + escapeHtml(s.note) : '') + '</p>' +
        '<div class="meta"><span class="swatch" style="background:' + s.colour + '"></span>' + pixelLabel((s.kind === 'pack' ? 'PACK · ' : s.kind === 'draft' ? 'DRAFT · ' : 'PROFILE · ') + it.games + (it.games === 1 ? ' GAME' : ' GAMES'), 2) + '</div>' +
        '<div class="cols"><div><div class="shots">' + s.palette.map(c => '<div class="shot" style="width:calc(44 * var(--u));height:calc(44 * var(--u));background:' + c + '"></div>').join('') + '</div></div>' +
        menuHTML(menu) + '</div>'
    } else {
      const g = it.game
      const rows = verificationRows(g)
      const dots = verificationDots(g)
      const meta = [g.rooms != null ? g.rooms + ' ROOMS' : null, g.endings != null ? g.endings + (g.endings === 1 ? ' ENDING' : ' ENDINGS') : null, g.style.label.toUpperCase(), moduleBadge(g)].filter(Boolean).join(' · ')
      panel.innerHTML = '<p class="premise">' + escapeHtml(g.premise) + '</p>' +
        '<div class="meta"><span class="swatch" style="background:' + g.style.colour + '"></span>' + pixelLabel(meta, 2) + '</div>' +
        '<div class="cols"><div><div class="checks">' + rows.map((r, i) => '<div class="check" data-tone="' + r.tone + '" title="' + escapeHtml(r.words) + '"><span class="dot is-' + dots[i] + '"></span>' + pixelLabel(r.label, 1.7) + '<span class="val">' + pixelLabel(r.value, 1.7) + '</span></div>').join('') + '</div>' +
        '<div class="shots">' + shotsFor(g).slice(0, 3).map(src => '<div class="shot" style="background-image:url(' + JSON.stringify(src).slice(1, -1) + ')"></div>').join('') + '</div></div>' +
        menuHTML(menu) + '</div>' +
        '<div class="confirm' + (state.confirm ? ' is-on' : '') + '"><p>Launch the macOS build outside Hermes? It runs as a normal app.</p><div class="row">' +
        '<span class="opt' + (state.confirm && state.confirm.yes ? ' is-on' : '') + '" data-yes="1">' + pixelLabel('LAUNCH', 2) + '</span>' +
        '<span class="opt' + (state.confirm && !state.confirm.yes ? ' is-on' : '') + '" data-yes="0">' + pixelLabel('CANCEL', 2) + '</span></div></div>'
    }
    panel.querySelectorAll('.item').forEach(n => n.addEventListener('click', ev => {
      ev.stopPropagation()
      dispatch({ type: 'menu_set', index: Number(n.dataset.index) })
      dispatch({ type: 'open' })
    }))
  }

  function menuHTML(menu) {
    const cur = menu[state.menu]
    // A group of buttons, NOT role="menu": the Desktop treats any [role=menu|listbox|dialog] in
    // the document as an open overlay and stands its own keys down (combo.ts OVERLAY_SURFACE).
    return '<div><div class="menu" role="group" aria-label="Game actions">' + menu.map((m, i) =>
      '<div class="item' + (i === state.menu ? ' is-on' : '') + (m.enabled ? '' : ' is-off') + '" role="button"' + (i === state.menu ? ' aria-current="true"' : '') + ' aria-disabled="' + (!m.enabled) + '" data-index="' + i + '">' +
      '<span class="cursor">' + pixelLabel('▶', 2) + '</span>' + pixelLabel(m.label, 2) + (m.tag ? '<span class="tag">' + pixelLabel(m.tag, 1.5) + '</span>' : '') + '</div>').join('') + '</div>' +
      '<div class="reason">' + (cur && !cur.enabled ? escapeHtml(cur.reason) : '') + '</div></div>'
  }

  let liveNew = false
  function liveNewCart(on) {
    const slot = slots['__new__@games']
    if (!slot) return
    const cart = slot.querySelector('.cart')
    if (on) {
      const styles = newGameStyles(cat)
      const sel = styles[state.newgame.style]
      cart.innerHTML = cartSVG({ uid: 'new-live', kind: 'new', shell: sel ? sel.colour : '#d9dee8', accent: sel ? sel.colour : '#ffc93c', title: 'NEW GAME', label: state.newgame.text, ariaLabel: 'New game' })
      fitCardTitles(cart)
      liveNew = true
    } else if (liveNew) {
      cart.innerHTML = cartFor({ type: 'new', id: '__new__' })
      fitCardTitles(cart)
      liveNew = false
    }
  }

  function renderNewGame() {
    const styles = newGameStyles(cat)
    const sel = styles[state.newgame.style]
    if (!ngPanel.querySelector('.label-input')) {
      ngPanel.innerHTML = '<div class="label-card"><textarea class="label-input" maxlength="280" spellcheck="true" placeholder="A keeper\'s last night on a frozen pier…" aria-label="Premise for the new game"></textarea></div>' +
        '<div class="styles-row"></div><div class="style-name"></div>' +
        '<div class="menu"><div class="item is-on give" role="button">' + '<span class="cursor">' + pixelLabel('▶', 2) + '</span>' + pixelLabel('GIVE TO HERMES', 2) + '</div></div>'
      const ta = ngPanel.querySelector('.label-input')
      ta.addEventListener('input', () => dispatch({ type: 'text', value: ta.value }))
      ngPanel.querySelector('.give').addEventListener('click', ev => { ev.stopPropagation(); dispatch({ type: 'open' }) })
    }
    liveNewCart(true)
    const ta = ngPanel.querySelector('.label-input')
    if (ta.value !== state.newgame.text) ta.value = state.newgame.text
    if (document.activeElement !== ta) setTimeout(() => ta.focus(), 0)
    ngPanel.querySelector('.styles-row').innerHTML = styles.map((s, i) => '<span class="chip' + (i === state.newgame.style ? ' is-on' : '') + '" data-index="' + i + '" title="' + escapeHtml(s.label) + '">' +
      s.palette.slice(0, 6).map(c => '<i style="background:' + c + '"></i>').join('') + '</span>').join('')
    ngPanel.querySelector('.style-name').innerHTML = sel ? pixelLabel('STYLE · ' + sel.label.toUpperCase(), 2) : ''
    ngPanel.querySelectorAll('.chip').forEach(n => n.addEventListener('click', ev => {
      ev.stopPropagation()
      dispatch({ type: 'move', dx: Number(n.dataset.index) - state.newgame.style })
    }))
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
  }

  // ---------------- effects ----------------
  function runEffects(fx, now) {
    for (const e of fx) {
      if (e.type === 'sound') sound.play(e.id)
      else if (e.type === 'bump') { bumpAt = now }
      else if (e.type === 'refilter') { enterAt = now; enterDir = 1; jumpScroll = true }
      else if (e.type === 'reshelf') { enterAt = now; enterDir = e.dir > 0 ? 1 : -1; jumpScroll = true }
      else if (e.type === 'handoff') {
        debug.handoffs.push({ kind: e.kind, text: e.text })
        if (hostApi.handoff) later(hostApi.handoff(e), r => (r && r.ok === false ? setNotice(r.message || 'COULD NOT OPEN A CHAT', 'warn') : null))
      } else if (e.type === 'reveal') {
        debug.reveals.push(e.id)
        if (hostApi.reveal) later(hostApi.reveal(e.id), r => setNotice(r && r.ok ? 'FOLDER OPENED' : (r && r.message) || 'FOLDER IS NOT ON THIS MACHINE', r && r.ok ? 'good' : 'warn'))
        else state = Object.assign({}, state, { notice: { text: 'FOLDER OPENS IN THE DESKTOP APP', tone: 'good' } })
      } else if (e.type === 'play') startPlay(e, now)
      else if (e.type === 'eject') {
        playPhase = null
        root.classList.remove('is-inserting')
        play.className = 'h64s-play'
        hideFrame()
        reclaimFocus()
        if (hostApi.eject) later(hostApi.eject(), null)
      }
    }
  }

  // Host calls may return values or promises; failures become a notice, never a throw.
  function later(value, then) {
    Promise.resolve(value).then(r => { if (!disposed && then) then(r) }).catch(err => {
      errors.push(String(err && err.message ? err.message : err))
      if (!disposed) setNotice('SOMETHING WENT WRONG', 'warn')
    })
  }
  function setNotice(text, tone) {
    state = Object.assign({}, state, { notice: { text, tone } })
    renderChrome()
  }

  function showFrame() {
    if (!frameUrl || disposed) return
    const content = play.querySelector('.content')
    if (hostApi.showFrame) {
      const r = content.getBoundingClientRect()
      const rr = root.getBoundingClientRect()
      hostApi.showFrame({ url: frameUrl, title: 'Hermes64 game', rect: { left: r.left - rr.left, top: r.top - rr.top, width: r.width, height: r.height } })
    } else if (!content.querySelector('iframe')) {
      const f = document.createElement('iframe')
      f.setAttribute('sandbox', 'allow-scripts')
      f.setAttribute('referrerpolicy', 'no-referrer')
      f.title = 'Hermes64 game'
      f.src = frameUrl
      content.innerHTML = ''
      content.appendChild(f)
    }
  }
  function hideFrame() {
    frameUrl = null
    if (hostApi.hideFrame) hostApi.hideFrame()
  }
  // A playing web build holds focus inside its frame; when it goes, the keyboard comes back
  // to the Studio (unless the user had already moved somewhere else, e.g. the composer).
  function reclaimFocus() {
    const a = document.activeElement
    if (!a || a === document.body || a === root || root.contains(a) || a.tagName === 'IFRAME') root.focus({ preventScroll: true })
  }
  // The play server's bridge (hold Esc inside the game) asks to eject. Accepted only from the
  // frame this Studio is showing, and only while playing.
  function isOurFrame(source) {
    if (!source) return false
    if (hostApi.isFrameSource) return !!hostApi.isFrameSource(source)
    return [...play.querySelectorAll('iframe')].some(f => f.contentWindow === source)
  }
  function onFrameMessage(ev) {
    if (disposed || state.view !== 'play' || !ev.data || ev.data.hermes64 !== 'eject' || !isOurFrame(ev.source)) return
    dispatch({ type: 'eject' })
  }

  function startPlay(e, now) {
    debug.plays.push({ id: e.id, target: e.target })
    if (e.target === 'macos') {
      if (hostApi.launchNative) later(hostApi.launchNative(e), r => setNotice(r && r.ok ? 'OPENED THE MACOS BUILD' : (r && r.message) || 'COULD NOT OPEN THE BUILD', r && r.ok ? 'good' : 'warn'))
      else state = Object.assign({}, state, { notice: { text: 'NATIVE LAUNCH HAPPENS IN THE DESKTOP APP', tone: 'good' } })
      return
    }
    const g = cat.games.find(x => x.id === e.id)
    const content = play.querySelector('.content')
    const img = new Image()
    img.alt = ''
    img.src = artFor(e.id)
    content.innerHTML = ''
    content.appendChild(img)
    const stamp = el('div', 'stamp', pixelLabel(g && g.sample ? 'SAMPLE BUILD · NOTHING TO RUN' : hostApi.play ? 'LOADING' : 'WEB EXPORT PLAYS HERE', 2))
    content.appendChild(stamp)
    frameUrl = null
    if (hostApi.play && !(g && g.sample)) {
      later(hostApi.play(e), r => {
        if (playPhase === null) return
        if (r && r.url) {
          frameUrl = r.url
          stamp.style.display = 'none'
          if (playPhase === 'run') showFrame()
        } else stamp.innerHTML = pixelLabel(((r && r.message) || 'COULD NOT START THE WEB BUILD').toUpperCase().slice(0, 40), 2)
      })
    }
    play.querySelector('.eject').innerHTML = glyphHTML(HINTS.eject, state.input) + pixelLabel('HOLD TO EJECT', 2)
    play.querySelector('.eject').onclick = () => dispatch({ type: 'eject' })
    playStart = now
    playPhase = reduced ? 'run' : 'insert'
    if (!reduced) root.classList.add('is-inserting')
    play.className = 'h64s-play phase-' + (reduced ? 'run' : 'insert')
  }

  // ---------------- dispatch ----------------
  function dispatch(action) {
    const now = clock()
    if (action.type === 'toggle_sound') {
      const onNow = sound.toggle()
      state = Object.assign({}, state, { notice: { text: onNow ? 'SOUND ON' : 'SOUND OFF', tone: 'good' } })
      renderChrome()
      return
    }
    if (loadError && action.type === 'open') { if (hostApi.reload) hostApi.reload(); else location.reload(); return }
    debug.actions++
    const before = state
    const r = reduce(state, action, cat, caps)
    state = r.state
    runEffects(r.effects, now)
    if (state.shelf !== before.shelf || state.filter !== before.filter) buildShelf(now)
    if (state !== before || r.effects.length) renderChrome()
  }
  debug.dispatch = dispatch
  debug.state = () => state

  // ---------------- input wiring ----------------
  root.addEventListener('keydown', ev => {
    // Inside Hermes Desktop the host's capture-phase keybinds see every key first. A key
    // the host claimed (defaultPrevented: PageUp/PageDown scroll the conversation, any
    // bare key the user bound) is the host's and is never handled a second time here.
    if (ev.defaultPrevented || ev.isComposing) return
    const view = state.jump ? 'jump' : state.help ? 'help' : state.bar != null ? 'bar' : state.view
    const a = keyAction(ev, view)
    if (!a) return
    ev.preventDefault()
    if (state.input !== 'keys') dispatch({ type: 'input', mode: 'keys' })
    dispatch(a)
  })
  title.querySelector('.title-input').addEventListener('input', ev => dispatch({ type: 'text', value: ev.target.value }))
  top.querySelectorAll('.h64s-nav').forEach(b => {
    b.addEventListener('click', ev => {
      ev.stopPropagation()
      dispatch({ type: 'nav', id: b.dataset.nav })
    })
    b.addEventListener('mouseenter', () => { tipHover = Number(b.dataset.index); renderChrome() })
    b.addEventListener('mouseleave', () => { tipHover = null; renderChrome() })
  })
  strip.addEventListener('click', ev => {
    const t = ev.target.closest('.thumb')
    if (!t || t.dataset.index == null) return
    const it = items()[Number(t.dataset.index)]
    if (it) dispatch({ type: 'select_id', id: it.id })
  })
  help.addEventListener('click', () => dispatch({ type: 'back' }))
  panel.addEventListener('click', ev => {
    const o = ev.target.closest('.opt')
    if (!o) return
    const yes = o.dataset.yes === '1'
    if (state.confirm && state.confirm.yes !== yes) dispatch({ type: 'move', dx: 1 })
    dispatch({ type: 'open' })
  })
  let wheelAt = 0
  root.addEventListener('wheel', ev => {
    if (state.view !== 'home' || state.bar != null || Math.abs(ev.deltaX) + Math.abs(ev.deltaY) < 8) return
    const now = clock()
    if (now - wheelAt < 140) return
    wheelAt = now
    dispatch({ type: 'move', dx: (Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY) > 0 ? 1 : -1 })
  }, { passive: true })
  const onResize = () => { if (disposed) return; measure(); setDrift(); stripWindow = -1; renderChrome(); if (playPhase === 'run') showFrame() }
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(onResize)
    ro.observe(root)
    disposers.push(() => ro.disconnect())
  } else {
    window.addEventListener('resize', onResize)
    disposers.push(() => window.removeEventListener('resize', onResize))
  }
  window.addEventListener('message', onFrameMessage)
  disposers.push(() => window.removeEventListener('message', onFrameMessage))
  if (motionQuery && motionQuery.addEventListener) {
    motionQuery.addEventListener('change', setDrift)
    disposers.push(() => motionQuery.removeEventListener('change', setDrift))
  }
  disposers.push(() => { if (driftAnim) driftAnim.cancel(); driftAnim = null })

  async function resolveArt() {
    // Nearest cards first, back-of-box shots last.
    const list = items()
    const pos = {}
    list.forEach((it, i) => { pos[it.id] = i })
    const at = selectedIndex(list, state)
    const rank = j => Math.abs((pos[j.key] == null ? 1e6 : pos[j.key]) - at) + (j.shot == null ? 0 : 1e5)
    const queue = pendingArt.slice().sort((a, b) => rank(a) - rank(b))
    const worker = async () => {
      while (queue.length && !disposed) {
        const job = queue.shift()
        let url = null
        try { url = await hostApi.image(job.src) } catch (err) { url = null }
        if (!url || disposed) continue
        if (job.shot == null) {
          art[job.key] = url
          artIsCapture[job.key] = true
          delete cartCache['game:' + job.key]
          const slot = slots[job.key + '@games']
          const it = cat.games.find(x => x.id === job.key)
          if (slot && it) { const cart = slot.querySelector('.cart'); cart.innerHTML = cartFor({ type: 'game', id: it.id, game: it }); fitCardTitles(cart) }
          stripDirty = true
        } else {
          shotsFor(gameById[job.key])[job.shot] = url
          if (state.view === 'detail') renderChrome()
        }
      }
    }
    await Promise.all([worker(), worker(), worker(), worker()])
  }

  // ---------------- frame loop ----------------
  function frame(now) {
    if (disposed) return
    debug.frames++
    const fStart = performance.now()
    try {
      if (stripDirty) { stripDirty = false; stripWindow = -1; renderChrome() }
      if (navigator.getGamepads) {
        const acts = pad.poll(navigator.getGamepads(), now, state.jump ? 'jump' : state.view)
        for (const a of acts) dispatch(a)
      }
      const list = items()
      const idx = selectedIndex(list, state)
      const L = layout
      const n = layoutCount(list)
      view0 = L.narrow ? idx : pageFor(idx, n, view0)
      if (jumpScroll) { scroll.jump(view0); jumpScroll = false }
      scroll.set(view0, now, reduced ? 0 : 190, 30, EASE.outCubic)
      const sc = scroll.value(now)
      const centre = L.narrow ? sc : sc + 1.5
      paintBudget = 2
      ensureSlots(centre, false)
      const waiting = Object.values(slots).filter(s => s.dataset.pending).sort((a, b) => Math.abs(a.dataset.index - centre) - Math.abs(b.dataset.index - centre))
      for (const s of waiting) {
        if (paintBudget <= 0) break
        const it = slotList[Number(s.dataset.index)]
        if (!it) continue
        const svg = cartFor(it)
        if (cartCache[it.type + ':' + it.id]) { const cart = s.querySelector('.cart'); cart.innerHTML = svg; fitCardTitles(cart); delete s.dataset.pending; stripDirty = true }
      }
      paintBudget = Infinity
      const detailish = state.view === 'detail' || state.view === 'newgame' || (state.view === 'play' && playPhase === 'insert')
      const enterT = reduced ? 1 : Math.min(1, (now - enterAt) / 260)
      // The selected card steps up to its enlarged size in three held frames.
      const pop = reduced ? 1 : Math.min(1, Math.floor(((now - selAt) / 110) * 3) / 3)
      Object.values(slots).concat(Array.from(shelfEl.querySelectorAll('.is-ghost-slot'))).forEach(s => {
        const i = Number(s.dataset.index)
        let x = L.narrow ? (i - sc) * L.pitch : (i - sc - 1.5) * L.pitch
        let scale = 1
        let y = 0
        let op = 1
        const focus = i === idx && !s.classList.contains('is-ghost-slot')
        if (focus && !detailish) { scale = 1 + 0.045 * pop; y = 2 * L.u * pop }
        if (detailish) {
          if (focus) {
            if (L.narrow) { x = 0; scale = 0.6; y = -(L.u * 158) } else { x = -360 * L.u; scale = 1.1; y = 10 * L.u }
          } else { op = 0; x += (i < idx ? -1 : 1) * 160 * L.u }
        }
        if (!reduced && enterT < 1) {
          // A new shelf rises in from below, selection first, in held 5-step frames.
          const k = Math.max(0, Math.min(1, (now - enterAt - Math.abs(i - idx) * 24) / 170))
          const e = EASE.outCubic(Math.floor(k * 5) / 5)
          y += (1 - e) * 36 * L.u * enterDir
          op *= 0.3 + 0.7 * e
        }
        if (focus && bumpAt && now - bumpAt < 240 && !reduced) x += Math.sin(((now - bumpAt) / 240) * Math.PI * 4) * 7 * L.u * (Math.floor((now - bumpAt) / 40) % 2 ? 1 : 0.5)
        if (Math.abs(x) > L.W * 0.9 + 400 * L.u) { s.style.visibility = 'hidden'; return }
        s.style.visibility = 'visible'
        s.style.transform = 'translate3d(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px,0) scale(' + scale.toFixed(3) + ')'
        s.style.opacity = op.toFixed(3)
        s.style.zIndex = String(focus ? 150 : 100 - Math.round(Math.abs(i - centre) * 2))
        s.classList.toggle('is-focus', focus && state.view !== 'play')
      })
      if (playPhase) {
        const t = now - playStart
        if (playPhase === 'insert') {
          // Pick the card up from the detail spot, carry it to the centre, tip it
          // back and push it down into the glowing slot; then lights out.
          const fly = Object.values(slots).find(s => Number(s.dataset.index) === idx)
          if (fly) {
            const q = k => Math.floor(Math.min(1, Math.max(0, k)) * 8) / 8
            const a1 = EASE.outCubic(q(t / 160))
            const a2 = EASE.inCubic(q((t - 160) / 240))
            const x = L.narrow ? 0 : -360 * L.u * (1 - a1)
            const y = -30 * L.u * a1 + a2 * 160 * L.u
            const k = 1.1 + 0.08 * a1 - 0.45 * a2
            fly.style.transform = 'translate3d(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px,0) scale(' + k.toFixed(3) + ') perspective(700px) rotateX(' + (a2 * 58).toFixed(1) + 'deg)'
            fly.style.opacity = t > 400 ? String(Math.max(0, 1 - Math.floor(((t - 400) / 48) * 3) / 3)) : '1'
            fly.style.zIndex = '200'
          }
          root.classList.toggle('is-slot-hot', t > 300)
          play.style.display = t > 440 ? 'block' : 'none'
          play.style.background = 'rgba(0,0,0,' + (Math.floor(Math.min(1, Math.max(0, (t - 440) / 160)) * 4) / 4).toFixed(2) + ')'
          if (t > 600) { playPhase = 'boot'; play.className = 'h64s-play phase-boot'; play.style.background = '#000'; root.classList.remove('is-inserting'); root.classList.remove('is-slot-hot') }
        } else if (playPhase === 'boot' && t > 1000) {
          playPhase = 'run'
          play.className = 'h64s-play phase-run'
          showFrame()
        }
      } else play.style.display = ''
      if (state.notice !== noticeRef) { noticeRef = state.notice; noticeAt = now }
      if (state.notice && now - noticeAt > 2600) {
        state = Object.assign({}, state, { notice: null })
        renderChrome()
      }
    } catch (err) {
      errors.push(String(err && err.stack ? err.stack : err))
    }
    const cost = performance.now() - fStart
    debug.frameMs = debug.frameMs == null ? cost : debug.frameMs * 0.9 + cost * 0.1
    debug.frameMaxMs = Math.max(debug.frameMaxMs || 0, cost)
    if (!manual && !disposed) rafId = requestAnimationFrame(frame)
  }

  // ---------------- scene from URL (for screenshots) ----------------
  measure()
  setDrift()
  buildShelf(clock() - 1000)
  if (params.view === 'detail' || params.view === 'newgame') {
    if (params.view === 'newgame') { state.sel.games = '__new__'; dispatch({ type: 'open' }) } else dispatch({ type: 'open' })
    if (params.menu) for (let i = 0; i < Number(params.menu); i++) dispatch({ type: 'vertical', dy: 1 })
    if (params.text) dispatch({ type: 'text', value: params.text })
    if (params.ngstyle) dispatch({ type: 'move', dx: Number(params.ngstyle) })
  }
  if (params.view === 'play') { dispatch({ type: 'open' }); dispatch({ type: 'open' }) }
  if (params.jump) { dispatch({ type: 'jump_open' }); dispatch({ type: 'text', value: params.jump }) }
  if (params.bar != null && state.view === 'home') { dispatch({ type: 'menu' }); for (let i = 0; i < Number(params.bar); i++) dispatch({ type: 'move', dx: 1 }) }
  if (params.help === '1') dispatch({ type: 'nav', id: 'help' })
  renderChrome()
  const settled = clock() - 2000
  view0 = layout.narrow ? selectedIndex(items(), state) : pageFor(selectedIndex(items(), state), layoutCount(items()), params.page != null ? Number(params.page) : view0)
  scroll.jump(view0)
  selAt = settled
  enterAt = params.enter === '1' ? clock() : settled
  root.focus()
  if (manual) {
    debug.advance = ms => { manualNow += ms; frame(manualNow); return manualNow }
    frame(manualNow)
  } else rafId = requestAnimationFrame(frame)
  if (pendingArt.length) resolveArt()
  debug.dispose = () => {
    if (disposed) return
    disposed = true
    if (rafId) cancelAnimationFrame(rafId)
    for (const d of disposers.splice(0)) { try { d() } catch (err) { /* already gone */ } }
    hideFrame()
    root.innerHTML = ''
    root.classList.remove('h64s')
  }
  debug.bootMs = Math.round(performance.now() - bootT0)
  debug.ready = true
  return debug
}
