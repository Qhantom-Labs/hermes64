// The Hermes64 box card: an original rectangular card with a white frame, pixel-
// stepped corners and a hard dark offset shadow. The top ~60% is a composed cover
// (art, title logotype, style band, corner mark); the strip below carries four
// verification dots and a module badge. Returned as an SVG string so the prototype
// and the desktop plugin draw byte-identical cards. The selected look (blue frame,
// tinted strip) is pure CSS on `.is-focus`, so selection never re-renders a card.
import { pixelPath, pixelWidth, escapeXml } from './pixelfont.js'

export const CARD_W = 236
export const CARD_H = 260
// The viewBox adds room for the focus ring (outside the frame) and the shadow.
export const CART_W = 250
export const CART_H = 274
const VIEW = '-4 -4 ' + CART_W + ' ' + CART_H
export const ART = { x: 8, y: 22, w: 220, h: 154 }
const INK = '#1b1d2c'
const TITLE_FONT = 'Avenir Next Condensed, Futura, Arial Narrow, Helvetica Neue, Arial, sans-serif'

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1, 7), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
function mix(a, b, t) {
  const x = hexToRgb(a)
  const y = hexToRgb(b)
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')
}
function lum(hex) {
  const c = hexToRgb(hex)
  return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255
}
function safeHex(h, fallback) {
  return typeof h === 'string' && /^#[0-9a-fA-F]{6}$/.test(h) ? h : fallback
}

// A rectangle with pixel-stepped corners: n steps of s units at each corner.
export function stepRect(x, y, w, h, n, s = 3) {
  const c = n * s
  let d = 'M' + (x + c) + ' ' + y + 'H' + (x + w - c)
  for (let i = 0; i < n; i++) d += 'v' + s + 'h' + s
  d += 'V' + (y + h - c)
  for (let i = 0; i < n; i++) d += 'h' + -s + 'v' + s
  d += 'H' + (x + c)
  for (let i = 0; i < n; i++) d += 'v' + -s + 'h' + -s
  d += 'V' + (y + c)
  for (let i = 0; i < n; i++) d += 'h' + s + 'v' + -s
  return d + 'Z'
}

function pixelText(text, x, y, scale, fill, outline) {
  const t = String(text).toUpperCase()
  const tr = 'translate(' + x.toFixed(2) + ' ' + y.toFixed(2) + ') scale(' + scale + ')'
  return (outline ? '<path transform="' + tr + '" fill="' + outline + '" stroke="' + outline + '" stroke-width="1.6" stroke-linejoin="round" d="' + pixelPath(t) + '"/>' : '') +
    '<path transform="' + tr + '" fill="' + fill + '" d="' + pixelPath(t) + '"/>'
}

// Split a title into at most two lines, balancing their lengths.
export function titleLines(title) {
  const t = String(title || '').toUpperCase().replace(/\s+/g, ' ').trim()
  if (t.length <= 11 || t.indexOf(' ') < 0) return [t]
  const words = t.split(' ')
  let best = [t]
  let bestW = Infinity
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ')
    const b = words.slice(i).join(' ')
    const w = Math.max(a.length, b.length)
    if (w < bestW) { bestW = w; best = [a, b] }
  }
  return best
}

// The title logotype: heavy condensed italic caps, gradient fill in the style's
// colour, a dark outline and a hard drop shadow. `data-maxw` lets the shell
// squeeze a line that measures wider than the art (fitCardTitles in app.js).
function logotype(id, title, pos, styleColour, opts = {}) {
  const lines = titleLines(title)
  const base = safeHex(styleColour, '#8a8fb8')
  const light = mix(base, '#ffffff', 0.82)
  const mid = mix(base, '#ffffff', lum(base) > 0.6 ? 0.1 : 0.35)
  const edge = opts.ink || mix(base, INK, 0.82)
  const size = lines.length > 1 ? 25 : lines[0].length > 8 ? 29 : 34
  const lead = size * 0.92
  const maxW = ART.w - 18
  const blockH = lead * (lines.length - 1) + size * 0.74
  const top = pos === 'bottom' ? ART.y + ART.h - 14 - blockH : ART.y + 10
  const cx = ART.x + ART.w / 2
  const fill = opts.fill || 'url(#' + id + '-t)'
  let s = '<linearGradient id="' + id + '-t" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.45" stop-color="' + light + '"/><stop offset="1" stop-color="' + mid + '"/></linearGradient>'
  s += '<g class="cart-logo" font-family="' + TITLE_FONT + '" font-weight="900" font-style="italic" font-size="' + size + '" text-anchor="middle" letter-spacing="0.5">'
  lines.forEach((ln, i) => {
    const y = (top + size * 0.74 + i * lead).toFixed(1)
    const t = escapeXml(ln)
    s += '<text x="' + (cx + 2) + '" y="' + (Number(y) + 3) + '" data-maxw="' + maxW + '" fill="' + INK + '" stroke="' + INK + '" stroke-width="6" stroke-linejoin="round" opacity="0.85">' + t + '</text>' +
      '<text x="' + cx + '" y="' + y + '" data-maxw="' + maxW + '" fill="' + fill + '" stroke="' + edge + '" stroke-width="5" stroke-linejoin="round" paint-order="stroke">' + t + '</text>'
  })
  return s + '</g>'
}

// The small corner mark: a tiny white card carrying a gold feather.
function cornerMark(x, y) {
  return '<g class="cart-mark" transform="translate(' + x + ' ' + y + ')">' +
    '<path d="' + stepRect(0, 0, 20, 20, 2, 2) + '" fill="#ffffff" stroke="' + INK + '" stroke-width="1.6"/>' +
    '<rect x="4" y="4" width="9" height="7" fill="#3f86f0"/>' +
    '<path d="M9 16C11 11 14 7 18 5C17 9 14 13 10 17Z" fill="#ffc93c" stroke="' + INK + '" stroke-width="1.1" stroke-linejoin="round"/></g>'
}

// Colour grade for runtime captures: saturation, optional warmth, a gamma lift,
// then an S-curve for punch. Pure SVG filter: no pixel reads, so it works on
// file:// pages and data URLs alike.
function gradeFilter(id, grade) {
  const g = Object.assign({ gamma: 0.8, gain: 1.06, lift: 0.02, saturation: 1.25, warmth: 0, contrast: 1.3 }, grade || {})
  const k = Math.max(0, Math.min(1, g.contrast - 1))
  const curve = []
  for (let i = 0; i <= 8; i++) { const x = i / 8; const sm = x * x * (3 - 2 * x); curve.push((x + (sm - x) * k * 1.6).toFixed(3)) }
  const fn = c => '<feFunc' + c + ' type="gamma" amplitude="' + g.gain + '" exponent="' + g.gamma + '" offset="' + g.lift + '"/>'
  const sc = c => '<feFunc' + c + ' type="table" tableValues="' + curve.map(v => Math.max(0, Math.min(1, Number(v)))).join(' ') + '"/>'
  return '<filter id="' + id + '-g" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">' +
    '<feColorMatrix type="saturate" values="' + g.saturation + '"/>' +
    (g.warmth ? '<feColorMatrix type="matrix" values="1 0 0 0 ' + g.warmth.toFixed(3) + ' 0 1 0 0 ' + (g.warmth * 0.25).toFixed(3) + ' 0 0 1 0 ' + (-g.warmth).toFixed(3) + ' 0 0 0 1 0"/>' : '') +
    '<feComponentTransfer>' + fn('R') + fn('G') + fn('B') + '</feComponentTransfer>' +
    '<feComponentTransfer>' + sc('R') + sc('G') + sc('B') + '</feComponentTransfer></filter>'
}

function artImage(id, spec) {
  const href = escapeXml(spec.coverHref)
  // finished box art is shown as is: no grade filter (cartSVG defines none for it), no subject crop
  const graded = spec.capture && !spec.boxArt ? ' filter="url(#' + id + '-g)"' : ''
  if (spec.focus && spec.capture && !spec.boxArt) {
    const f = spec.focus
    const W = spec.srcW || 320
    const H = spec.srcH || 240
    return '<svg x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" viewBox="' + f.join(' ') + '" preserveAspectRatio="xMidYMid slice">' +
      '<image class="cart-cover" href="' + href + '" x="0" y="0" width="' + W + '" height="' + H + '"' + graded + '/></svg>'
  }
  return '<image class="cart-cover" href="' + href + '" x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" preserveAspectRatio="xMidYMid slice"' + graded + '/>'
}

function dotsHTML(dots, dashed) {
  return dots.map((d, i) => {
    const cx = 21 + i * 21
    if (d === 'on') return '<circle class="cart-dot is-on" cx="' + cx + '" cy="232" r="7.4" fill="#36c26e" stroke="#16603a" stroke-width="2"/><rect x="' + (cx - 3.5) + '" y="227" width="3" height="2.4" fill="#ffffff" opacity="0.85"/>'
    if (d === 'fail') return '<circle class="cart-dot is-fail" cx="' + cx + '" cy="232" r="7" fill="none" stroke="#e0483a" stroke-width="2.6"/><path d="M' + (cx - 4) + ' 236L' + (cx + 4) + ' 228" stroke="#e0483a" stroke-width="2.4"/>'
    return '<circle class="cart-dot is-off" cx="' + cx + '" cy="232" r="7" fill="none" stroke="#858b99" stroke-width="2.4"' + (dashed ? ' stroke-dasharray="3 2.4"' : '') + '/>'
  }).join('')
}

function badge(text, opts = {}) {
  const t = String(text).toUpperCase()
  const sc = 1.6
  const w = pixelWidth(t) * sc + 14
  const x = 226 - w
  const fill = opts.fill || '#5a5e6b'
  return '<g class="cart-badge">' +
    '<path d="' + stepRect(x, 219, w, 26, 2, 2) + '" fill="' + (opts.dashed ? 'none' : fill) + '" stroke="' + (opts.dashed ? '#9aa0ad' : INK) + '" stroke-width="' + (opts.dashed ? 2 : 1.6) + '"' + (opts.dashed ? ' stroke-dasharray="3 2.4"' : '') + '/>' +
    pixelText(t, x + 7, 225.6, sc, opts.dashed ? '#7d8392' : opts.ink || '#ffffff', opts.dashed ? null : opts.outline || '#2a2c36') +
    '</g>'
}

function sampleTag(text) {
  const t = String(text).toUpperCase()
  const w = pixelWidth(t) * 1.4 + 10
  return '<g class="cart-tape"><path d="' + stepRect(8, 5, w, 13, 1, 2) + '" fill="#c8402f"/>' + pixelText(t, 13, 8, 1.4, '#fff8e8', null) + '</g>'
}

function frameParts() {
  return '<path class="card-shadow" d="' + stepRect(6, 6, CARD_W, CARD_H, 3) + '"/>' +
    '<path class="card-frame" d="' + stepRect(0, 0, CARD_W, CARD_H, 3) + '"/>' +
    '<path class="card-tint" d="' + stepRect(3, 3, CARD_W - 6, CARD_H - 6, 2) + '"/>'
}

function wrapWords(text, maxChars, maxLines) {
  const words = String(text).replace(/\s+/g, ' ').trim().split(' ').filter(Boolean)
  const lines = []
  let cur = ''
  for (const w0 of words) {
    let w = w0
    while (w.length > maxChars) { if (cur) { lines.push(cur); cur = '' } lines.push(w.slice(0, maxChars)); w = w.slice(maxChars) }
    if (!cur) cur = w
    else if ((cur + ' ' + w).length <= maxChars) cur += ' ' + w
    else { lines.push(cur); cur = w }
  }
  if (cur) lines.push(cur)
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines)
    kept[maxLines - 1] = kept[maxLines - 1].slice(0, Math.max(1, maxChars - 1)) + '…'
    return kept
  }
  return lines
}

// spec: { uid, kind: 'game'|'new'|'style'|'ghost'|'error'|'pending', shell (style colour),
//         title, coverHref, capture, focus, srcW, srcH, grade, titlePos, dots, badge,
//         palette, badgeText, badgeFill, tape, label, ariaLabel }
export function cartSVG(spec) {
  const uid = String(spec.uid || 'c').replace(/[^a-zA-Z0-9_-]/g, '')
  const kind = spec.kind || 'game'
  const label = escapeXml(spec.ariaLabel || spec.title || 'Game')
  if (kind === 'ghost') {
    return '<svg class="cart-svg is-ghost" viewBox="' + VIEW + '" aria-hidden="true">' +
      '<path d="' + stepRect(0, 0, CARD_W, CARD_H, 3) + '" fill="rgba(255,255,255,0.38)" stroke="rgba(40,70,140,0.38)" stroke-width="2.5" stroke-dasharray="8 6"/>' +
      '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="rgba(120,160,230,0.12)" stroke="rgba(40,70,140,0.22)" stroke-width="2" stroke-dasharray="5 5"/></svg>'
  }
  const id = 'h64c-' + uid
  const style = safeHex(spec.shell, '#8a8fb8')
  const pos = spec.titlePos === 'bottom' ? 'bottom' : 'top'
  let defs = '<clipPath id="' + id + '-a"><rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '"/></clipPath>' +
    '<radialGradient id="' + id + '-v" cx="0.5" cy="0.5" r="0.75"><stop offset="0.55" stop-color="#0a0c1e" stop-opacity="0"/><stop offset="1" stop-color="#0a0c1e" stop-opacity="0.42"/></radialGradient>' +
    '<linearGradient id="' + id + '-b" x1="0" y1="' + (pos === 'bottom' ? 1 : 0) + '" x2="0" y2="' + (pos === 'bottom' ? 0 : 1) + '"><stop offset="0" stop-color="' + mix(style, '#0a0c1e', 0.55) + '" stop-opacity="0.62"/><stop offset="0.42" stop-color="' + mix(style, '#0a0c1e', 0.55) + '" stop-opacity="0"/></linearGradient>'
  let art = ''
  let strip = ''
  let logo = ''
  if (kind === 'new') {
    const accent = safeHex(spec.accent, '#ffc93c')
    art += '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="#fffaf0"/>'
    for (let y = ART.y + 46; y < ART.y + ART.h - 6; y += 15) art += '<rect x="' + ART.x + '" y="' + y + '" width="' + ART.w + '" height="1.3" fill="#c9d9ee"/>'
    art += '<rect x="' + (ART.x + 24) + '" y="' + ART.y + '" width="1.5" height="' + ART.h + '" fill="#f1a39a"/>'
    if (spec.label) {
      art += '<g class="cart-written" font-family="Chalkboard SE, Marker Felt, Comic Sans MS, Avenir Next, sans-serif" font-size="12.5" fill="#23243e">' +
        wrapWords(spec.label, 26, 6).map((ln, i) => '<text x="' + (ART.x + 30) + '" y="' + (ART.y + 58 + i * 15) + '">' + escapeXml(ln) + '</text>').join('') + '</g>'
    } else {
      art += '<g class="cart-plus" transform="translate(118 112)"><path d="M-9 -27h18v18h18v18h-18v18h-18v-18h-18v-18h18z" fill="' + INK + '" transform="translate(3 3)"/>' +
        '<path d="M-9 -27h18v18h18v18h-18v18h-18v-18h-18v-18h18z" fill="' + accent + '" stroke="' + INK + '" stroke-width="2.6" stroke-linejoin="round"/>' +
        '<path d="M-6 -24h10v4h-10z" fill="#ffffff" opacity="0.85"/></g>'
    }
    art += '<rect x="' + ART.x + '" y="' + (ART.y + ART.h - 7) + '" width="' + ART.w + '" height="7" fill="' + (spec.label ? style : '#d9dee8') + '"/>'
    logo = logotype(id, spec.title || 'NEW GAME', 'top', '#ffffff', { fill: '#ffffff', ink: INK })
    strip = dotsHTML(['off', 'off', 'off', 'off'], true) + badge('NEW', { dashed: true })
  } else if (kind === 'error') {
    art += '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="#4a3a48"/>' +
      '<path d="M40 40L120 120L96 150M180 30L140 96L176 130L150 176" stroke="' + INK + '" stroke-width="3" fill="none"/>'
    for (let x = -10; x < 240; x += 16) art += '<path d="M' + x + ' 176L' + (x + 8) + ' 176L' + (x + 18) + ' 166L' + (x + 10) + ' 166Z" fill="#ffcf4a"/>'
    logo = '<g font-family="' + TITLE_FONT + '" font-weight="900" font-size="80" text-anchor="middle"><text x="120" y="128" fill="#ffffff" stroke="' + INK + '" stroke-width="6" paint-order="stroke">?</text></g>'
    strip = dotsHTML(['off', 'off', 'off', 'off'], true) + badge('ERROR', { fill: '#c8402f' })
  } else {
    // game, style or pending (plain art until the cover is painted)
    // Finished box art from the cover tool already carries its logotype, band and corner mark: it is shown as is,
    // with no grade, vignette, style band, corner mark or title of the cartridge's own (docs/COVER-INTEGRATION.md).
    const boxed = !!(spec.boxArt && spec.coverHref)
    if (spec.capture && spec.coverHref && !boxed) defs += gradeFilter(id, spec.grade)
    art += '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="' + mix(style, '#0a0c1e', 0.25) + '"/>'
    if (spec.coverHref) art += artImage(id, spec)
    if (spec.capture && spec.coverHref && !boxed) {
      const mood = (spec.grade && spec.grade.mood) || 'day'
      const box = 'x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '"'
      if (mood === 'dusk') {
        // a sunset multiplied into the sky: pale skies turn amber and rose, so light
        // landmarks stand out as silhouettes
        defs += '<linearGradient id="' + id + '-k" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d9583a" stop-opacity="0.9"/><stop offset="0.38" stop-color="#ff9a52" stop-opacity="0.75"/><stop offset="0.62" stop-color="#ffd08a" stop-opacity="0.15"/><stop offset="1" stop-color="#3a1d2e" stop-opacity="0.55"/></linearGradient>'
        art += '<rect ' + box + ' fill="url(#' + id + '-k)" style="mix-blend-mode:multiply"/>'
      } else if (mood === 'night') {
        defs += '<linearGradient id="' + id + '-k" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d1840" stop-opacity="0.75"/><stop offset="0.45" stop-color="#2a4a9a" stop-opacity="0.12"/><stop offset="1" stop-color="#0d1840" stop-opacity="0.7"/></linearGradient>'
        art += '<rect ' + box + ' fill="url(#' + id + '-k)" style="mix-blend-mode:multiply"/>'
      } else {
        // painted light over a capture: a soft-light sky wash in the style colour
        defs += '<linearGradient id="' + id + '-k" x1="0" y1="0" x2="0.25" y2="1"><stop offset="0" stop-color="' + mix(style, '#fff6dc', 0.55) + '" stop-opacity="0.95"/><stop offset="0.5" stop-color="' + mix(style, '#fff6dc', 0.2) + '" stop-opacity="0.25"/><stop offset="1" stop-color="' + mix(style, '#0a0c1e', 0.6) + '" stop-opacity="0.8"/></linearGradient>'
        art += '<rect ' + box + ' fill="url(#' + id + '-k)" style="mix-blend-mode:soft-light"/>'
      }
      // a soft spotlight on the subject (the middle of the chosen crop)
      defs += '<radialGradient id="' + id + '-s" cx="0.5" cy="0.56" r="0.55"><stop offset="0" stop-color="#ffffff" stop-opacity="0.6"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>'
      art += '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="url(#' + id + '-s)" style="mix-blend-mode:soft-light"/>'
    }
    if (!boxed) {
      art += '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="url(#' + id + '-v)"/>' +
        '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="url(#' + id + '-b)"/>'
      // style band along the bottom edge: the style colour with a highlight line
      art += '<rect x="' + ART.x + '" y="' + (ART.y + ART.h - 8) + '" width="' + ART.w + '" height="8" fill="' + style + '"/>' +
        '<rect x="' + ART.x + '" y="' + (ART.y + ART.h - 8) + '" width="' + ART.w + '" height="1.5" fill="#ffffff" opacity="0.55"/>' +
        '<rect x="' + ART.x + '" y="' + (ART.y + ART.h - 1.5) + '" width="' + ART.w + '" height="1.5" fill="' + INK + '" opacity="0.35"/>'
      art += pos === 'bottom' ? cornerMark(ART.x + 6, ART.y + 6) : cornerMark(ART.x + 6, ART.y + ART.h - 34)
      logo = logotype(id, spec.title || '', pos, style)
    } else logo = ''
    if (kind === 'style') {
      const pal = (spec.palette || []).slice(0, 7)
      strip = pal.map((c, i) => '<path d="' + stepRect(13 + i * 17, 223, 13, 18, 1, 2) + '" fill="' + safeHex(c, '#888888') + '" stroke="' + INK + '" stroke-width="1.4"/>').join('')
      if (spec.badgeText) strip += badge(spec.badgeText, spec.badgeFill ? { fill: spec.badgeFill, ink: INK, outline: '#ffffff' } : { dashed: true })
    } else {
      strip = dotsHTML(spec.dots || ['off', 'off', 'off', 'off'], false) + badge(spec.badge || 'STORY')
    }
  }
  let s = '<svg class="cart-svg is-' + kind + '" viewBox="' + VIEW + '" role="img" aria-label="' + label + '"><defs>' + defs + '</defs>' + frameParts() +
    '<g clip-path="url(#' + id + '-a)">' + art + '<rect class="card-art-tint" x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '"/>' + logo + '</g>' +
    '<rect x="' + ART.x + '" y="' + ART.y + '" width="' + ART.w + '" height="' + ART.h + '" fill="none" stroke="' + INK + '" stroke-opacity="0.55" stroke-width="1.5"/>' +
    strip
  if (spec.tape) s += sampleTag(spec.tape)
  return s + '</svg>'
}
