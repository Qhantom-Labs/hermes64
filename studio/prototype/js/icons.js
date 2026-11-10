// Original pixel icons, the Hermes64 Studio mark, and control-hint glyphs.
// Bitmaps are authored here; no console, controller or vendor iconography.
import { pixelPath, pixelWidth, escapeXml } from './pixelfont.js'
import { MODULES } from './model.js'
import { MARK_SVG } from './pattern.js'

const BITMAPS = {
  all: [
    '....#####....',
    '...#.....#...',
    '..#########..',
    '.#.........#.',
    '#############',
    '#...........#',
    '#..#######..#',
    '#..#.....#..#',
    '#..#######..#',
    '#...........#',
    '#############'
  ],
  mine: [
    '......#......',
    '.....###.....',
    '....#####....',
    '...#######...',
    '..#########..',
    '.###########.',
    '...#######...',
    '...#.....#...',
    '...#.###.#...',
    '...#.#.#.#...',
    '...#######...'
  ],
  status: [
    '......#......',
    '......#......',
    '.###########.',
    '#...........#',
    '#..###.###..#',
    '#..###.###..#',
    '#...........#',
    '#...#####...#',
    '#...........#',
    '.###########.',
    '..##.....##..'
  ]
}

function bitmap(rows) {
  let d = ''
  rows.forEach((row, r) => {
    let c = 0
    while (c < row.length) {
      if (row[c] !== '#') { c++; continue }
      let e = c
      while (e < row.length && row[e] === '#') e++
      d += 'M' + c + ' ' + r + 'h' + (e - c) + 'v1h-' + (e - c) + 'z'
      c = e
    }
  })
  return d
}

const STYLE_CHIPS = ['#ff6b5e', '#ffcf4a', '#7ed67a', '#6fd3ff', '#8e7bff', '#f4efe4']

export function iconSVG(name, size = 26) {
  const head = '<svg class="icon icon-' + name + '" viewBox="0 0 13 11" width="' + size + '" height="' + Math.round(size * 11 / 13) + '" shape-rendering="crispEdges" aria-hidden="true">'
  if (name === 'style') {
    let s = head
    STYLE_CHIPS.forEach((c, i) => {
      const x = (i % 3) * 4.5
      const y = Math.floor(i / 3) * 5.5
      s += '<rect x="' + (x + 0.5) + '" y="' + (y + 0.5) + '" width="3.4" height="4.2" fill="' + c + '" stroke="currentColor" stroke-width="1"/>'
    })
    return s + '</svg>'
  }
  if (name === 'modules') {
    let s = head
    MODULES.forEach((m, i) => {
      const cx = 1.9 + i * 3.1
      s += '<circle cx="' + cx + '" cy="5.5" r="1.45" fill="' + m.colour + '" stroke="currentColor" stroke-width="0.9"/>'
    })
    return s + '<rect x="0.4" y="2.6" width="12.2" height="5.8" rx="1.4" fill="none" stroke="currentColor" stroke-width="0.8"/></svg>'
  }
  const rows = BITMAPS[name] || BITMAPS.all
  return head + '<path fill="currentColor" d="' + bitmap(rows) + '"/></svg>'
}

const INK = '#1b1d2c'

function stepped(x, y, w, h, n, st) {
  const c = n * st
  let d = 'M' + (x + c) + ' ' + y + 'H' + (x + w - c)
  for (let i = 0; i < n; i++) d += 'v' + st + 'h' + st
  d += 'V' + (y + h - c)
  for (let i = 0; i < n; i++) d += 'h' + -st + 'v' + st
  d += 'H' + (x + c)
  for (let i = 0; i < n; i++) d += 'v' + -st + 'h' + -st
  d += 'V' + (y + c)
  for (let i = 0; i < n; i++) d += 'h' + st + 'v' + -st
  return d + 'Z'
}

// The mark: a small Hermes64 box card, tilted, with a three-feather wing.
function markGroup() {
  return '<g transform="rotate(-8 26 34)">' +
    '<path d="' + stepped(5, 7, 40, 52, 2, 3) + '" fill="' + INK + '"/>' +
    '<path d="' + stepped(1, 3, 40, 52, 2, 3) + '" fill="#ffffff" stroke="' + INK + '" stroke-width="2.6"/>' +
    '<rect x="6" y="9" width="30" height="24" fill="#3f86f0" stroke="' + INK + '" stroke-width="1.6"/>' +
    '<path d="M7 28L15 20L21 25L28 17L35 24L35 32L7 32Z" fill="#9fe0ff"/><circle cx="29" cy="14" r="2.6" fill="#fff1a8"/>' +
    '<circle cx="9" cy="44" r="2.6" fill="#36c26e" stroke="' + INK + '" stroke-width="1.3"/><circle cx="16" cy="44" r="2.4" fill="none" stroke="' + INK + '" stroke-width="1.3"/><circle cx="23" cy="44" r="2.4" fill="none" stroke="' + INK + '" stroke-width="1.3"/>' +
    '<rect x="28" y="40" width="9" height="8" fill="#5a5e6b"/></g>' +
    '<path d="M40 22C46 12 54 7 62 6C58 13 51 19 43 25Z" fill="#ffd23f" stroke="' + INK + '" stroke-width="2" stroke-linejoin="round"/>' +
    '<path d="M42 30C48 23 55 20 62 20C58 26 51 30 44 32Z" fill="#ffb43a" stroke="' + INK + '" stroke-width="2" stroke-linejoin="round"/>' +
    '<path d="M43 37C48 33 54 32 59 33C55 37 49 39 44 39Z" fill="#ff8a3d" stroke="' + INK + '" stroke-width="2" stroke-linejoin="round"/>'
}

export function logoSVG(size = 40) {
  return '<svg class="logo-mark" viewBox="0 0 64 64" width="' + size + '" height="' + size + '" aria-hidden="true">' + markGroup() + '</svg>'
}

// The wordmark: "HERMES" in chunky H64 Pixel letters (sunny gold-to-orange, dark
// outline, stepped 3-D extrusion), a sky-blue "64" sticker, and STUDIO / QHANTOM
// LABS beneath, with the small Qhantom Labs mark (traced, see pattern.js) before
// QHANTOM LABS. Original; deliberately unlike any console logo.
export function wordmarkSVG() {
  const sc = 6.6
  const word = 'HERMES'
  const ww = pixelWidth(word) * sc
  const x0 = 74
  const y0 = 6
  const d = pixelPath(word)
  const at = (dx, dy) => 'translate(' + (x0 + dx) + ' ' + (y0 + dy) + ') scale(' + sc + ')'
  let s = '<svg class="h64s-wordmark" viewBox="0 0 410 80" role="img" aria-label="Hermes64 Studio, Qhantom Labs">' +
    '<defs><linearGradient id="h64s-wm-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff6c2"/><stop offset="0.3" stop-color="#ffd23f"/><stop offset="0.72" stop-color="#ff9f2e"/><stop offset="1" stop-color="#ff6b3d"/></linearGradient></defs>' +
    '<g transform="translate(2 4)">' + markGroup() + '</g><g shape-rendering="crispEdges">'
  for (let k = 6; k >= 1; k--) s += '<path transform="' + at(k, k) + '" fill="' + (k > 3 ? '#0f1020' : INK) + '" d="' + d + '"/>'
  for (const [dx, dy] of [[-2.5, 0], [2.5, 0], [0, -2.5], [0, 2.5], [-2.5, -2.5], [2.5, -2.5], [-2.5, 2.5], [2.5, 2.5]]) s += '<path transform="' + at(dx, dy) + '" fill="' + INK + '" d="' + d + '"/>'
  s += '<path transform="' + at(0, 0) + '" fill="url(#h64s-wm-g)" d="' + d + '"/>' +
    '<path transform="' + at(0, 0) + '" fill="#ffffff" opacity="0.55" d="' + pixelPath(word).replace(/M(\d+) (\d+)h1v1h-1z/g, (m, x, y) => (y === '0' ? m : '')) + '"/></g>'
  // "64" sticker
  const cx = x0 + ww + 30
  s += '<g transform="rotate(12 ' + cx + ' 26)"><circle cx="' + (cx + 3) + '" cy="29" r="23" fill="' + INK + '"/><circle cx="' + cx + '" cy="26" r="23" fill="#35b6ff" stroke="' + INK + '" stroke-width="3"/>' +
    '<circle cx="' + cx + '" cy="26" r="17" fill="none" stroke="#ffffff" stroke-opacity="0.55" stroke-width="2" stroke-dasharray="3 3"/>' +
    '<g shape-rendering="crispEdges"><path transform="translate(' + (cx - 16 + 1.5) + ' ' + (16 + 1.5) + ') scale(3)" fill="' + INK + '" d="' + pixelPath('64') + '"/>' +
    '<path transform="translate(' + (cx - 16) + ' 16) scale(3)" fill="#ffffff" d="' + pixelPath('64') + '"/></g></g>'
  // STUDIO · QHANTOM LABS
  let x = x0 + 2
  const sub = 2.2
  s += '<g shape-rendering="crispEdges">'
  for (const ch of 'STUDIO') {
    s += '<path transform="translate(' + (x + 1) + ' 64) scale(' + sub + ')" fill="#ffffff" d="' + pixelPath(ch) + '"/><path transform="translate(' + x + ' 63) scale(' + sub + ')" fill="' + INK + '" d="' + pixelPath(ch) + '"/>'
    x += (pixelWidth(ch) + 2) * sub
  }
  // the mark in the label's slate ink, centred on its letters, sky-coloured creases where the rings cross
  const mh = 13
  const ms = mh / MARK_SVG.h
  s += '<g class="h64s-wm-mark" shape-rendering="geometricPrecision" transform="translate(' + (x + 10) + ' ' + (71.6 - mh / 2) + ') scale(' + ms + ')">' +
    '<path fill="#41507a" fill-rule="evenodd" d="' + MARK_SVG.shape + '"/>' +
    '<path fill="none" stroke="#eef5ff" stroke-width="' + (0.9 / ms).toFixed(2) + '" stroke-linecap="round" d="' + MARK_SVG.edges + '"/></g>'
  s += '<path transform="translate(' + (x + 10 + MARK_SVG.w * ms + 4) + ' 66) scale(1.6)" fill="#41507a" d="' + pixelPath('QHANTOM LABS') + '"/></g>'
  return s + '</svg>'
}

// The four icon-bar icons (Games, Styles, Filters, Help): original drawings on a
// 24x24 grid with chunky dark outlines and flat fills.
export function navIconSVG(name) {
  let b = ''
  if (name === 'games') {
    b = '<path d="' + stepped(10, 1.5, 11, 15, 1, 1.5) + '" fill="#c9d6f2" stroke="' + INK + '" stroke-width="1.8"/>' +
      '<path d="' + stepped(6.5, 4.5, 11, 15, 1, 1.5) + '" fill="#eef3fc" stroke="' + INK + '" stroke-width="1.8"/>' +
      '<path d="' + stepped(3, 7.5, 11, 15, 1, 1.5) + '" fill="#ffffff" stroke="' + INK + '" stroke-width="1.8"/>' +
      '<rect x="5" y="9.5" width="7" height="6" fill="#3f86f0"/><path d="M5 15.5L8 12.5L10 14L12 12V15.5Z" fill="#9fe0ff"/>' +
      '<circle cx="6" cy="19" r="1" fill="' + INK + '"/><circle cx="8.6" cy="19" r="1" fill="' + INK + '"/><rect x="10.2" y="18" width="2.6" height="2" fill="#5a5e6b"/>'
  } else if (name === 'styles') {
    b = '<path d="M12 2.5C5.5 2.5 2 7.5 2 12C2 17.5 6.5 21.5 11.5 21.5C13.6 21.5 13.8 19.6 12.8 18.2C11.8 16.8 12.6 15 14.6 15H17.5C20.5 15 22 12.8 22 10.2C22 5.6 17.8 2.5 12 2.5Z" fill="#ffffff" stroke="' + INK + '" stroke-width="1.8" stroke-linejoin="round"/>' +
      '<circle cx="7" cy="11" r="2.1" fill="#ff5e57" stroke="' + INK + '" stroke-width="1"/><circle cx="10.5" cy="6.8" r="2.1" fill="#ffd23f" stroke="' + INK + '" stroke-width="1"/>' +
      '<circle cx="15.8" cy="7.2" r="2.1" fill="#36c26e" stroke="' + INK + '" stroke-width="1"/><circle cx="7.6" cy="16.2" r="2" fill="#35b6ff" stroke="' + INK + '" stroke-width="1"/>'
  } else if (name === 'filters') {
    b = '<path d="M2.5 3.5H21.5L14.2 12.4V19.2L9.8 21.4V12.4Z" fill="#ffffff" stroke="' + INK + '" stroke-width="1.8" stroke-linejoin="round"/>' +
      '<path d="M5.5 6.2H18.5" stroke="#3f86f0" stroke-width="1.8"/><path d="M8.4 9.2H15.6" stroke="#3f86f0" stroke-width="1.6"/>'
  } else {
    b = '<path d="M3 3H21V16H11.5L6.5 20.5V16H3Z" fill="#ffd23f" stroke="' + INK + '" stroke-width="1.8" stroke-linejoin="round"/>' +
      '<path transform="translate(9.4 5.6) scale(1.1)" fill="' + INK + '" shape-rendering="crispEdges" d="' + pixelPath('?') + '"/>'
  }
  return '<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">' + b + '</svg>'
}

const SMALL = {
  key: ['.##....', '#..#...', '#..####', '.##.#.#', '.......'],
  bot: ['...#...', '#######', '#.#.#.#', '#######', '.#...#.'],
  chips: ['##.##..', '##.##..', '.......', '##.##..', '##.##..'],
  person: ['..###..', '..###..', '.......', '.#####.', '.#####.']
}

export function smallIcon(name, scale = 2) {
  const rows = SMALL[name] || SMALL.key
  return '<svg class="small-icon" viewBox="0 0 7 5" width="' + 7 * scale + '" height="' + 5 * scale + '" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="' + bitmap(rows) + '"/></svg>'
}

// The counter's two labels ("UNTESTED" "11/14") at the largest pixel size, from `start` down,
// whose total width fits `room` stage units (pixelLabel widths plus the gap between them). A
// name too long even at the smallest size is cut and ends in "..", so the plate never clips.
export const COUNTER_SIZES = [2.4, 2, 1.6]
export function counterFit(head, pos, room, gap, start = 2.4) {
  const width = (h, s) => (pixelWidth(h) + 1 + pixelWidth(pos) + 1) * s + gap
  const sizes = COUNTER_SIZES.filter(s => s <= start)
  for (const s of sizes) if (width(head, s) <= room) return { head, size: s, width: +width(head, s).toFixed(2) }
  const s = sizes[sizes.length - 1]
  let h = String(head)
  while (h.length > 1 && width(h.trimEnd() + '..', s) > room) h = h.slice(0, -1)
  h = h.trimEnd() + '..'
  return { head: h, size: s, width: +width(h, s).toFixed(2) }
}

export function pixelLabel(text, scale = 2, cls = 'px') {
  const w = pixelWidth(text) + 1
  const W = +(w * scale).toFixed(2)
  const H = +(8 * scale).toFixed(2)
  return '<svg class="' + cls + '" viewBox="0 0 ' + w + ' 8" width="' + W + '" height="' + H + '" style="width:calc(' + W + ' * var(--u, 1px));height:calc(' + H + ' * var(--u, 1px))" shape-rendering="crispEdges" role="img" aria-label="' + escapeXml(text) + '">' +
    '<path class="px-shadow" d="' + pixelPath(text, 1, 1) + '"/><path class="px-ink" d="' + pixelPath(text) + '"/></svg>'
}

// Control glyphs. Keyboard shows keycaps; gamepad shows generic face buttons
// and shoulder pills (A/B/LB/RB as on the W3C "standard" gamepad mapping).
export function glyphHTML(glyph, mode) {
  const kind = mode === 'pad' ? glyph.pad : glyph.keys
  return kind.map(k => {
    if (k.shape === 'round') return '<span class="glyph glyph-round glyph-' + escapeXml(k.tone || 'plain') + '">' + pixelLabel(k.text, 2, 'px glyph-px') + '</span>'
    if (k.shape === 'pill') return '<span class="glyph glyph-pill">' + pixelLabel(k.text, 2, 'px glyph-px') + '</span>'
    if (k.shape === 'dpad') return '<span class="glyph glyph-dpad glyph-dpad-' + escapeXml(k.dir || 'h') + '"><i></i><i></i></span>'
    return '<span class="glyph glyph-key">' + pixelLabel(k.text, 2, 'px glyph-px') + '</span>'
  }).join('')
}

// label: the plain words shown beside the glyphs (title case, like a console menu).
export const HINTS = {
  browse: { label: 'Browse', keys: [{ text: '←→' }], pad: [{ shape: 'dpad', dir: 'h' }] },
  open: { label: 'Open', keys: [{ text: 'ENTER' }], pad: [{ shape: 'round', text: 'A', tone: 'a' }] },
  select: { label: 'Select', keys: [{ text: 'ENTER' }], pad: [{ shape: 'round', text: 'A', tone: 'a' }] },
  retry: { label: 'Try Again', keys: [{ text: 'ENTER' }], pad: [{ shape: 'round', text: 'A', tone: 'a' }] },
  back: { label: 'Game List', keys: [{ text: 'ESC' }], pad: [{ shape: 'round', text: 'B', tone: 'b' }] },
  menu: { label: 'Menu', keys: [{ text: 'TAB' }], pad: [{ shape: 'pill', text: 'START' }] },
  prev: { label: 'Previous Filter', keys: [{ text: 'Q' }], pad: [{ shape: 'pill', text: 'LB' }] },
  next: { label: 'Next Filter', keys: [{ text: 'E' }], pad: [{ shape: 'pill', text: 'RB' }] },
  choose: { label: 'Choose', keys: [{ text: '↑↓' }], pad: [{ shape: 'dpad', dir: 'v' }] },
  across: { label: 'Choose', keys: [{ text: '←→' }], pad: [{ shape: 'dpad', dir: 'h' }] },
  hand: { label: 'Give to Hermes', keys: [{ text: 'ENTER' }], pad: [{ shape: 'round', text: 'A', tone: 'a' }] },
  cancel: { label: 'Cancel', keys: [{ text: 'ESC' }], pad: [{ shape: 'round', text: 'B', tone: 'b' }] },
  close: { label: 'Close', keys: [{ text: 'ESC' }], pad: [{ shape: 'round', text: 'B', tone: 'b' }] },
  style: { label: 'Style', keys: [{ text: '↑↓' }], pad: [{ shape: 'dpad', dir: 'v' }] },
  eject: { label: 'Hold to Eject', keys: [{ text: 'ESC' }], pad: [{ shape: 'round', text: 'B', tone: 'b' }] },
  find: { label: 'Find', keys: [{ text: '/' }], pad: [{ shape: 'pill', text: 'LT' }, { shape: 'pill', text: 'RT' }] },
  page: { label: 'Page', keys: [{ text: 'SHIFT' }, { text: '←→' }], pad: [{ shape: 'pill', text: 'LT' }, { shape: 'pill', text: 'RT' }] },
  type: { label: 'Type a Name', keys: [{ text: 'A-Z' }], pad: [{ shape: 'pill', text: 'LT' }, { shape: 'pill', text: 'RT' }] }
}
