// Procedural cover painter: original low-poly "painted" scenes at a 160x120
// internal resolution, finished with a 4x4 ordered dither into 5 bits per
// channel (a 16-bit framebuffer look). Deterministic for a given recipe/seed.
// Shared verbatim with desktop/plugin.js. Draws only shapes: no images, no fonts.

export const COVER_W = 160
export const COVER_H = 120

function hashSeed(text) {
  let h = 2166136261
  const s = String(text)
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function rng(seed) {
  let a = hashSeed(seed) || 1
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function rgb(hex) {
  const n = parseInt(String(hex).slice(1, 7), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function mix(a, b, t) {
  const x = rgb(a)
  const y = rgb(b)
  const c = x.map((v, i) => Math.round(v + (y[i] - v) * t))
  return '#' + c.map(v => v.toString(16).padStart(2, '0')).join('')
}

function shade(hex, amt) {
  return amt >= 0 ? mix(hex, '#ffffff', amt) : mix(hex, '#000000', -amt)
}

// Box-art grade for every recipe colour: lift the darks (night scenes become a
// bright, readable night), add saturation, keep the light end where it is.
function boxArtColour(hex) {
  const c = rgb(hex).map(v => v / 255)
  const max = Math.max(c[0], c[1], c[2])
  const min = Math.min(c[0], c[1], c[2])
  let h = 0
  let sat = 0
  const l = (max + min) / 2
  const d = max - min
  if (d > 0) {
    sat = d / (1 - Math.abs(2 * l - 1))
    if (max === c[0]) h = ((c[1] - c[2]) / d) % 6
    else if (max === c[1]) h = (c[2] - c[0]) / d + 2
    else h = (c[0] - c[1]) / d + 4
    h *= 60
  }
  const L = 0.15 + 0.85 * l
  const S = Math.min(1, sat * 1.3 + (sat > 0.05 ? 0.06 : 0))
  const C = (1 - Math.abs(2 * L - 1)) * S
  const X = C * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = L - C / 2
  const hp = ((h % 360) + 360) % 360
  const [r, g, b] = hp < 60 ? [C, X, 0] : hp < 120 ? [X, C, 0] : hp < 180 ? [0, C, X] : hp < 240 ? [0, X, C] : hp < 300 ? [X, 0, C] : [C, 0, X]
  return '#' + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round((v + m) * 255))).toString(16).padStart(2, '0')).join('')
}
function boxArtRecipe(value) {
  if (typeof value === 'string') return /^#[0-9a-fA-F]{6}$/.test(value) ? boxArtColour(value) : value
  if (Array.isArray(value)) return value.map(boxArtRecipe)
  if (value && typeof value === 'object') {
    const out = {}
    for (const k of Object.keys(value)) out[k] = boxArtRecipe(value[k])
    return out
  }
  return value
}

function alpha(hex, a) {
  const c = rgb(hex)
  return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'
}

function poly(ctx, pts, fill) {
  ctx.beginPath()
  ctx.moveTo(pts[0][0], pts[0][1])
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
  ctx.closePath()
  ctx.fillStyle = fill
  ctx.fill()
}

function rect(ctx, x, y, w, h, fill) {
  ctx.fillStyle = fill
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h))
}

function disc(ctx, x, y, r, fill) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
}

function glow(ctx, x, y, r, col, strength) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r)
  g.addColorStop(0, alpha(col, strength))
  g.addColorStop(1, alpha(col, 0))
  ctx.fillStyle = g
  ctx.fillRect(x - r, y - r, r * 2, r * 2)
}

// --- terrain layers -------------------------------------------------------

function ridge(rand, n, base, height, jag) {
  const pts = []
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * (COVER_W + 20) - 10
    const peak = i % 2 === 1
    const h = height * (peak ? 0.55 + rand() * 0.45 : 0.15 + rand() * 0.35 * jag)
    pts.push([x, base - h])
  }
  return pts
}

function layerMountains(ctx, L, rand, sunX, fog, fogT) {
  const base = L.base
  const col = mix(L.colour, fog, fogT)
  const pts = ridge(rand, L.peaks || 7, base, L.height, L.jag == null ? 0.7 : L.jag)
  poly(ctx, [[-10, base + 2]].concat(pts, [[COVER_W + 10, base + 2]]), col)
  for (let i = 1; i < pts.length - 1; i += 2) {
    const p = pts[i]
    const l = pts[i - 1]
    const r = pts[i + 1]
    const litLeft = sunX < p[0]
    poly(ctx, [p, l, [l[0] + (p[0] - l[0]) * 0.5, base + 2]], shade(col, litLeft ? 0.14 : -0.12))
    poly(ctx, [p, r, [p[0] + (r[0] - p[0]) * 0.5, base + 2]], shade(col, litLeft ? -0.12 : 0.14))
    if (L.snow) poly(ctx, [p, [p[0] - (p[0] - l[0]) * 0.28, p[1] + (l[1] - p[1]) * 0.28], [p[0] + (r[0] - p[0]) * 0.28, p[1] + (r[1] - p[1]) * 0.28]], mix(L.snow, fog, fogT * 0.6))
  }
}

function layerHills(ctx, L, rand, sunX, fog, fogT) {
  const col = mix(L.colour, fog, fogT)
  const pts = []
  const ph = rand() * 6.28
  const freq = L.freq || 1.6
  for (let x = -4; x <= COVER_W + 4; x += 8) {
    const y = L.base - L.height * (0.55 + 0.45 * Math.sin(ph + (x / COVER_W) * freq * 6.28)) - rand() * 1.5
    pts.push([x, y])
  }
  poly(ctx, [[-4, L.base + 2]].concat(pts, [[COVER_W + 4, L.base + 2]]), col)
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i]
    const b = pts[i + 1]
    const up = b[1] < a[1]
    poly(ctx, [a, b, [b[0], L.base + 2], [a[0], L.base + 2]], shade(col, (up === (sunX > a[0]) ? 0.08 : -0.06) * (i % 2 ? 1 : 0.6)))
  }
  if (L.rim) {
    ctx.strokeStyle = alpha(L.rim, 0.55)
    ctx.lineWidth = 1
    ctx.beginPath()
    pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1] + 0.5) : ctx.moveTo(p[0], p[1] + 0.5)))
    ctx.stroke()
  }
}

function layerSea(ctx, L, rand, sun, fog, fogT) {
  const top = L.base - L.height
  const g = ctx.createLinearGradient(0, top, 0, L.base)
  g.addColorStop(0, mix(L.colour, fog, fogT + 0.25))
  g.addColorStop(1, shade(L.colour, -0.15))
  ctx.fillStyle = g
  ctx.fillRect(0, top, COVER_W, L.height + 2)
  for (let i = 0; i < 26; i++) {
    const y = top + 2 + Math.floor(rand() * (L.height - 3))
    const x = rand() * COVER_W
    rect(ctx, x, y, 3 + rand() * 9, 1, alpha(shade(L.colour, 0.45), 0.55))
  }
  if (sun) {
    for (let y = top + 1; y < L.base; y += 2) {
      const w = 2 + (y - top) * 0.25 + rand() * 3
      rect(ctx, sun.x - w / 2 + (rand() - 0.5) * 3, y, w, 1, alpha(sun.colour, 0.55))
    }
  }
}

function layerPines(ctx, L, rand, sunX, fog, fogT) {
  const col = mix(L.colour, fog, fogT)
  const n = L.count || 9
  for (let i = 0; i < n; i++) {
    const x = (L.from == null ? 0 : L.from) + rand() * ((L.to == null ? COVER_W : L.to) - (L.from || 0))
    const h = L.height * (0.6 + rand() * 0.5)
    const w = h * 0.42
    const y = L.base + rand() * 3
    for (let k = 0; k < 3; k++) {
      const ty = y - h * (k * 0.28)
      const tw = w * (1 - k * 0.24)
      poly(ctx, [[x, ty - h * 0.42], [x - tw / 2, ty], [x + tw / 2, ty]], shade(col, -0.05 + k * 0.05))
      poly(ctx, [[x, ty - h * 0.42], [x, ty], [x + (sunX > x ? tw / 2 : -tw / 2), ty]], shade(col, 0.1 + k * 0.03))
      if (L.snow) poly(ctx, [[x, ty - h * 0.42], [x - tw * 0.18, ty - h * 0.3], [x + tw * 0.18, ty - h * 0.3]], L.snow)
    }
    rect(ctx, x - 0.5, y, 1.5, 3, shade(col, -0.35))
  }
}

function layerMesas(ctx, L, rand, sunX, fog, fogT) {
  const col = mix(L.colour, fog, fogT)
  const sides = [[-6, 30 + rand() * 18], [COVER_W - 26 - rand() * 18, COVER_W + 6]]
  for (const [x0, x1] of sides) {
    const top = L.base - L.height * (0.7 + rand() * 0.3)
    poly(ctx, [[x0, L.base + 2], [x0 + 3, top], [x1 - 3, top - 2], [x1, L.base + 2]], col)
    for (let y = top + 6; y < L.base; y += 7) rect(ctx, x0 + 2, y, x1 - x0 - 4, 1, shade(col, -0.12))
    rect(ctx, x0 + 3, top, x1 - x0 - 6, 2, shade(col, 0.18))
    if (sunX < COVER_W / 2 === x0 > COVER_W / 2) rect(ctx, x0 + 3, top + 2, (x1 - x0) * 0.35, L.base - top, alpha('#000000', 0.12))
  }
}

function layerCave(ctx, L, rand, sunX, fog, fogT) {
  const col = mix(L.colour, fog, fogT)
  const pts = []
  for (let i = 0; i <= 12; i++) {
    const x = (i / 12) * (COVER_W + 10) - 5
    pts.push([x, (i % 2 ? 6 + rand() * L.height : 2 + rand() * 6)])
  }
  poly(ctx, [[-5, -2]].concat(pts, [[COVER_W + 5, -2]]), col)
  for (let i = 1; i < pts.length; i += 2) poly(ctx, [pts[i], [pts[i][0] - 3, pts[i - 1][1]], [pts[i][0], pts[i - 1][1]]], shade(col, 0.12))
}

function ground(ctx, top, colour, fog, rand, tiles) {
  const g = ctx.createLinearGradient(0, top, 0, COVER_H)
  g.addColorStop(0, mix(colour, fog, 0.45))
  g.addColorStop(1, shade(colour, -0.28))
  ctx.fillStyle = g
  ctx.fillRect(0, top, COVER_W, COVER_H - top)
  if (tiles) {
    // Perspective rows suggest a tiled low-res ground texture.
    let y = top + 2
    let step = 2
    let k = 0
    while (y < COVER_H) {
      rect(ctx, 0, y, COVER_W, 1, alpha(k % 2 ? '#ffffff' : '#000000', 0.05))
      y += step
      step += 1
      k++
    }
    for (let i = 0; i < 40; i++) {
      const y2 = top + 3 + rand() * (COVER_H - top - 3)
      rect(ctx, rand() * COVER_W, y2, 1 + (y2 - top) / 18, 1, alpha(shade(colour, 0.3), 0.35))
    }
  }
}

// --- landmarks (all original, simple silhouettes) --------------------------

function windows(ctx, rand, x, y, w, h, n, light) {
  for (let i = 0; i < n; i++) {
    const wx = x + 1 + Math.floor(rand() * Math.max(1, w - 3))
    const wy = y + 1 + Math.floor(rand() * Math.max(1, h - 3))
    rect(ctx, wx, wy, 2, 2, light)
    glow(ctx, wx + 1, wy + 1, 4, light, 0.35)
  }
}

const LANDMARKS = {
  windtower(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    for (let i = 0; i < 4; i++) {
      const hx = x - 34 * s + i * 17 * s + rand() * 4
      const hw = 14 * s + rand() * 4
      const hh = 10 * s + rand() * 6
      rect(ctx, hx, base - hh, hw, hh, shade(m.colour, i % 2 ? 0.06 : -0.04))
      disc(ctx, hx + hw / 2, base - hh, hw / 2.6, shade(m.colour, 0.1))
      rect(ctx, hx + hw * 0.4, base - hh * 0.55, 3, hh * 0.55, shade(m.colour, -0.45))
      if (rand() > 0.4) rect(ctx, hx + 2, base - hh + 3, 2, 2, m.light)
    }
    const tw = 9 * s
    const th = 38 * s
    rect(ctx, x + 8 * s, base - th, tw, th, shade(m.colour, 0.08))
    rect(ctx, x + 8 * s + tw * 0.62, base - th, tw * 0.38, th, shade(m.colour, -0.1))
    for (let k = 0; k < 3; k++) rect(ctx, x + 9 * s, base - th + 2 + k * 3, tw - 2, 1, shade(m.colour, -0.5))
    rect(ctx, x + 7 * s, base - th - 2, tw + 2, 2, shade(m.colour, 0.2))
    glow(ctx, x + 12 * s, base - th * 0.5, 10, m.light, 0.22)
  },
  headframe(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    const h = 46 * s
    ctx.strokeStyle = m.colour
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(x - 12 * s, base); ctx.lineTo(x, base - h); ctx.lineTo(x + 12 * s, base)
    ctx.moveTo(x - 8 * s, base - h * 0.35); ctx.lineTo(x + 8 * s, base - h * 0.35)
    ctx.moveTo(x - 5 * s, base - h * 0.65); ctx.lineTo(x + 5 * s, base - h * 0.65)
    ctx.moveTo(x, base - h); ctx.lineTo(x + 22 * s, base - 8 * s)
    ctx.stroke()
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.arc(x, base - h, 5 * s, 0, Math.PI * 2); ctx.stroke()
    rect(ctx, x + 18 * s, base - 16 * s, 22 * s, 16 * s, shade(m.colour, 0.12))
    poly(ctx, [[x + 16 * s, base - 16 * s], [x + 29 * s, base - 24 * s], [x + 42 * s, base - 16 * s]], shade(m.colour, -0.1))
    windows(ctx, rand, x + 18 * s, base - 15 * s, 22 * s, 12 * s, 2, m.light)
    poly(ctx, [[x - 40 * s, base], [x - 40 * s, base - 12 * s], [x - 30 * s, base - 18 * s], [x - 20 * s, base - 12 * s], [x - 20 * s, base]], shade(m.colour, -0.25))
    glow(ctx, x - 30 * s, base - 6 * s, 12, m.light, 0.5)
    rect(ctx, x - 33 * s, base - 9 * s, 6 * s, 9 * s, alpha(m.light, 0.85))
    for (let i = 0; i < 3; i++) rect(ctx, x - 70 * s + i * 11 * s, base - 5 * s, 8 * s, 4 * s, shade(m.colour, 0.2))
  },
  station(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    disc(ctx, x, base, 26 * s, shade(m.colour, 0.05))
    disc(ctx, x - 6 * s, base - 8 * s, 12 * s, alpha('#ffffff', 0.12))
    rect(ctx, x - 30 * s, base - 1, 60 * s, 6, shade(m.colour, -0.2))
    for (let i = -2; i <= 2; i++) {
      disc(ctx, x + i * 9 * s, base - 12 * s + Math.abs(i) * 3 * s, 2.4 * s, m.light)
      glow(ctx, x + i * 9 * s, base - 12 * s + Math.abs(i) * 3 * s, 7, m.light, 0.35)
    }
    rect(ctx, x + 24 * s, base - 5 * s, 26 * s, 5 * s, shade(m.colour, -0.05))
    disc(ctx, x + 52 * s, base - 3 * s, 9 * s, shade(m.colour, 0.02))
    disc(ctx, x + 52 * s, base - 5 * s, 2 * s, m.light)
    rect(ctx, x - 1, base - 44 * s, 2, 18 * s, shade(m.colour, -0.2))
    disc(ctx, x, base - 44 * s, 2.5, m.light)
    glow(ctx, x, base - 44 * s, 9, m.light, 0.5)
  },
  volcano(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    poly(ctx, [[x - 50 * s, base], [x - 9 * s, base - 46 * s], [x + 9 * s, base - 46 * s], [x + 50 * s, base]], m.colour)
    poly(ctx, [[x - 9 * s, base - 46 * s], [x + 9 * s, base - 46 * s], [x + 50 * s, base], [x + 8 * s, base]], shade(m.colour, -0.18))
    glow(ctx, x, base - 48 * s, 22, m.light, 0.65)
    rect(ctx, x - 8 * s, base - 47 * s, 16 * s, 2, m.light)
    for (let i = 0; i < 4; i++) {
      ctx.strokeStyle = alpha(m.light, 0.8)
      ctx.lineWidth = 1
      ctx.beginPath()
      const sx = x - 4 * s + i * 3 * s
      ctx.moveTo(sx, base - 45 * s)
      ctx.lineTo(sx - 10 * s + rand() * 20 * s, base - 20 * s + rand() * 10)
      ctx.stroke()
    }
    // kite glider above the island
    const kx = x + 34 * s
    const ky = base - 70 * s
    poly(ctx, [[kx, ky - 6], [kx - 9, ky + 2], [kx, ky], [kx + 9, ky + 2]], shade(m.kite || '#fff4dc', 0))
    poly(ctx, [[kx, ky - 6], [kx, ky], [kx + 9, ky + 2]], shade(m.kite || '#fff4dc', -0.2))
  },
  clocktower(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    rect(ctx, x - 7 * s, base - 50 * s, 14 * s, 50 * s, m.colour)
    rect(ctx, x + 2 * s, base - 50 * s, 5 * s, 50 * s, shade(m.colour, -0.15))
    poly(ctx, [[x - 9 * s, base - 50 * s], [x, base - 64 * s], [x + 9 * s, base - 50 * s]], shade(m.colour, -0.25))
    disc(ctx, x, base - 40 * s, 5 * s, '#fff6dd')
    ctx.strokeStyle = shade(m.colour, -0.5)
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(x, base - 40 * s); ctx.lineTo(x, base - 43.5 * s); ctx.moveTo(x, base - 40 * s); ctx.lineTo(x + 2.5 * s, base - 40 * s); ctx.stroke()
    glow(ctx, x, base - 40 * s, 12, m.light, 0.3)
    for (let i = 0; i < 6; i++) {
      const hx = x - 64 * s + i * 24 * s + rand() * 6
      if (Math.abs(hx - x) < 14 * s) continue
      const hw = 13 * s
      rect(ctx, hx, base - 10 * s, hw, 10 * s, shade(m.colour, 0.15))
      poly(ctx, [[hx - 2, base - 10 * s], [hx + hw / 2, base - 17 * s], [hx + hw + 2, base - 10 * s]], shade(m.roof || '#9e3b2f', i % 2 ? 0 : -0.1))
      if (rand() > 0.3) rect(ctx, hx + 4 * s, base - 7 * s, 2, 2, m.light)
    }
  },
  stilts(ctx, m, rand, base) {
    for (let i = 0; i < 3; i++) {
      const x = (m.x + i * 0.22) * COVER_W - 30
      const s = (m.scale || 1) * (1 - i * 0.12)
      const y = base - 12 * s
      for (let k = 0; k < 4; k++) rect(ctx, x + k * 5 * s, y, 1, 14 * s, shade(m.colour, -0.3))
      rect(ctx, x - 2 * s, y - 9 * s, 20 * s, 9 * s, m.colour)
      poly(ctx, [[x - 4 * s, y - 9 * s], [x + 8 * s, y - 16 * s], [x + 20 * s, y - 9 * s]], shade(m.colour, -0.2))
      rect(ctx, x + 6 * s, y - 6 * s, 3 * s, 3 * s, m.light)
      glow(ctx, x + 7 * s, y - 5 * s, 9, m.light, 0.45)
    }
    for (let i = 0; i < 26; i++) {
      const rx = rand() * COVER_W
      rect(ctx, rx, base - 2 - rand() * 8, 1, 10, alpha(shade(m.colour, -0.4), 0.8))
    }
  },
  greenhouse(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    const glass = m.colour
    poly(ctx, [[x - 22 * s, base], [x - 22 * s, base - 24 * s], [x, base - 62 * s], [x + 22 * s, base - 24 * s], [x + 22 * s, base]], alpha(glass, 0.55))
    ctx.strokeStyle = shade(m.frame || '#f4efe4', 0)
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x - 22 * s, base); ctx.lineTo(x - 22 * s, base - 24 * s); ctx.lineTo(x, base - 62 * s); ctx.lineTo(x + 22 * s, base - 24 * s); ctx.lineTo(x + 22 * s, base)
    for (let k = 1; k < 4; k++) { ctx.moveTo(x - 22 * s + k * 11 * s, base); ctx.lineTo(x - 22 * s + k * 11 * s, base - 24 * s - (k === 2 ? 38 * s : 19 * s)) }
    ctx.moveTo(x - 22 * s, base - 12 * s); ctx.lineTo(x + 22 * s, base - 12 * s)
    ctx.moveTo(x - 22 * s, base - 24 * s); ctx.lineTo(x + 22 * s, base - 24 * s)
    ctx.stroke()
    poly(ctx, [[x - 18 * s, base - 30 * s], [x - 8 * s, base - 46 * s], [x - 4 * s, base - 40 * s], [x - 14 * s, base - 26 * s]], alpha('#ffffff', 0.35))
    for (let i = 0; i < 7; i++) disc(ctx, x - 16 * s + rand() * 32 * s, base - 3 - rand() * 16 * s, 2 + rand() * 2.5, shade(m.leaf || '#4fa35a', rand() * 0.2))
    glow(ctx, x, base - 30 * s, 26, m.light, 0.28)
  },
  trail(ctx, m, rand, base) {
    ctx.strokeStyle = alpha(m.colour, 0.9)
    ctx.lineWidth = 3
    ctx.beginPath()
    ctx.moveTo(10, COVER_H)
    ctx.bezierCurveTo(70, COVER_H - 20, 20, base + 6, 90, base - 4)
    ctx.bezierCurveTo(120, base - 10, 110, base - 26, 140, base - 34)
    ctx.stroke()
    const flags = [[36, COVER_H - 18], [74, base + 2], [118, base - 18], [140, base - 34]]
    flags.forEach(([fx, fy], i) => {
      const s = 1 - i * 0.18
      rect(ctx, fx, fy - 12 * s, 1, 12 * s, '#f4efe4')
      poly(ctx, [[fx + 1, fy - 12 * s], [fx + 8 * s, fy - 10 * s], [fx + 1, fy - 8 * s]], i % 2 ? m.light : m.flag || '#ff5a5a')
    })
    poly(ctx, [[132, base - 34], [140, base - 46], [148, base - 34]], alpha(m.light, 0.5))
  },
  arena(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    ctx.fillStyle = shade(m.colour, -0.1)
    ctx.beginPath(); ctx.ellipse(x, base - 4 * s, 46 * s, 12 * s, 0, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = shade(m.floor || '#c9a36b', 0)
    ctx.beginPath(); ctx.ellipse(x, base - 4 * s, 36 * s, 8 * s, 0, 0, Math.PI * 2); ctx.fill()
    for (let i = 0; i < 9; i++) {
      const a = Math.PI + (i / 8) * Math.PI
      const px = x + Math.cos(a) * 44 * s
      const py = base - 4 * s + Math.sin(a) * 11 * s
      rect(ctx, px - 2 * s, py - 16 * s, 4 * s, 16 * s, shade(m.colour, i % 2 ? 0.1 : -0.05))
      if (i % 2 === 0) {
        disc(ctx, px, py - 18 * s, 1.6 * s, m.light)
        glow(ctx, px, py - 18 * s, 7, m.light, 0.6)
      }
    }
    rect(ctx, x - 1, base - 10 * s, 2, 6 * s, '#20212e')
    rect(ctx, x + 6 * s, base - 9 * s, 2, 5 * s, '#5a1f24')
  },
  harbor(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    for (let i = 0; i < 5; i++) {
      const hx = x - 40 * s + i * 16 * s
      const hh = 10 * s + (i % 3) * 4 * s
      rect(ctx, hx, base - hh, 13 * s, hh, shade(m.colour, (i % 2 ? 0.1 : -0.02)))
      poly(ctx, [[hx - 1, base - hh], [hx + 6.5 * s, base - hh - 6 * s], [hx + 14 * s, base - hh]], shade(m.roof || '#3e5f8a', i % 2 ? -0.1 : 0.05))
      if (rand() > 0.35) rect(ctx, hx + 4 * s, base - hh + 3 * s, 2, 2, m.light)
    }
    rect(ctx, x - 6 * s, base - 22 * s, 18 * s, 6 * s, '#f4efe4')
    rect(ctx, x - 4 * s, base - 20 * s, 14 * s, 2, m.sign || '#d84a3a')
    rect(ctx, x + 40 * s, base, 30 * s, 2, shade(m.colour, -0.3))
    for (let k = 0; k < 4; k++) rect(ctx, x + 42 * s + k * 8 * s, base, 1, 6, shade(m.colour, -0.4))
  },
  observatory(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    rect(ctx, x - 16 * s, base - 14 * s, 32 * s, 14 * s, m.colour)
    ctx.fillStyle = shade(m.colour, 0.15)
    ctx.beginPath(); ctx.arc(x, base - 14 * s, 16 * s, Math.PI, 0); ctx.fill()
    poly(ctx, [[x - 2 * s, base - 30 * s], [x + 3 * s, base - 30 * s], [x + 3 * s, base - 14 * s], [x - 2 * s, base - 14 * s]], '#11131f')
    ctx.strokeStyle = shade(m.colour, 0.35)
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(x, base - 20 * s); ctx.lineTo(x + 8 * s, base - 36 * s); ctx.stroke()
    rect(ctx, x - 10 * s, base - 8 * s, 3, 3, m.light)
    glow(ctx, x - 9 * s, base - 7 * s, 8, m.light, 0.5)
  },
  mushrooms(ctx, m, rand, base) {
    for (let i = 0; i < 7; i++) {
      const x = 10 + rand() * (COVER_W - 20)
      const s = 0.5 + rand() * 0.9
      const cap = i % 2 ? m.colour : m.alt || '#7fffd4'
      rect(ctx, x - 1.5 * s, base - 14 * s, 3 * s, 14 * s, '#e9dcc8')
      ctx.fillStyle = cap
      ctx.beginPath(); ctx.ellipse(x, base - 14 * s, 9 * s, 5 * s, 0, Math.PI, 0); ctx.fill()
      glow(ctx, x, base - 14 * s, 16 * s, cap, 0.45)
      disc(ctx, x - 3 * s, base - 16 * s, 1, '#ffffff')
    }
  },
  dome(ctx, m, rand, base) {
    const x = m.x * COVER_W
    const s = m.scale || 1
    ctx.fillStyle = m.colour
    ctx.beginPath(); ctx.arc(x, base, 18 * s, Math.PI, 0); ctx.fill()
    rect(ctx, x - 4 * s, base - 8 * s, 8 * s, 8 * s, m.light)
    glow(ctx, x, base - 6 * s, 20, m.light, 0.45)
  }
}

function figure(ctx, f, base) {
  const x = f.x * COVER_W
  const y = base + (f.dy || 6)
  const c = f.colour || '#d9def0'
  rect(ctx, x - 2, y - 9, 4, 5, c)
  rect(ctx, x - 2, y - 4, 4, 4, shade(c, -0.35))
  rect(ctx, x - 1, y - 8, 2, 2, '#0b0c14')
  rect(ctx, x - 2, y, 1, 2, '#1b1d2a')
  rect(ctx, x + 1, y, 1, 2, '#1b1d2a')
  if (f.lamp) {
    disc(ctx, x + 3, y - 4, 1, f.lamp)
    glow(ctx, x + 3, y - 4, 9, f.lamp, 0.55)
  }
}

function particles(ctx, p, rand) {
  const n = p.count || 30
  for (let i = 0; i < n; i++) {
    const x = rand() * COVER_W
    const y = rand() * COVER_H
    if (p.kind === 'snow' || p.kind === 'dust') rect(ctx, x, y, rand() > 0.85 ? 2 : 1, 1, alpha(p.colour || '#ffffff', 0.55 + rand() * 0.4))
    else if (p.kind === 'fireflies' || p.kind === 'embers' || p.kind === 'spores') {
      disc(ctx, x, y, 0.8, p.colour)
      glow(ctx, x, y, 4, p.colour, 0.5)
    } else if (p.kind === 'bubbles') {
      ctx.strokeStyle = alpha(p.colour || '#dff6ff', 0.6)
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.arc(x, y, 1 + rand() * 1.6, 0, Math.PI * 2); ctx.stroke()
    } else if (p.kind === 'leaves') rect(ctx, x, y, 2, 1, alpha(p.colour || '#ff9a3c', 0.85))
  }
}

function aurora(ctx, a, rand) {
  for (let band = 0; band < 3; band++) {
    const y0 = 14 + band * 9 + rand() * 6
    for (let x = 0; x < COVER_W; x += 2) {
      const y = y0 + Math.sin(x / 17 + band * 1.7) * 6
      const g = ctx.createLinearGradient(0, y - 10, 0, y + 6)
      g.addColorStop(0, alpha(a.colour, 0))
      g.addColorStop(0.7, alpha(a.colour, 0.28 - band * 0.06))
      g.addColorStop(1, alpha(a.colour, 0))
      ctx.fillStyle = g
      ctx.fillRect(x, y - 10, 2, 16)
    }
  }
}

function clouds(ctx, c, rand, horizon) {
  for (let i = 0; i < (c.count || 3); i++) {
    const x = rand() * COVER_W
    const y = 10 + rand() * (horizon * 0.45)
    const w = 18 + rand() * 26
    poly(ctx, [[x - w / 2, y], [x - w / 3, y - 4], [x, y - 6], [x + w / 3, y - 4], [x + w / 2, y]], alpha(c.colour, 0.85))
    rect(ctx, x - w / 2, y, w, 2, alpha(shade(c.colour, -0.25), 0.7))
  }
}

const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]

// 4x4 ordered dither down to 5 bits/channel, plus a soft corner vignette.
function finish(ctx) {
  const img = ctx.getImageData(0, 0, COVER_W, COVER_H)
  const d = img.data
  const cx = COVER_W / 2
  const cy = COVER_H / 2
  for (let y = 0; y < COVER_H; y++) {
    for (let x = 0; x < COVER_W; x++) {
      const i = (y * COVER_W + x) * 4
      const dx = (x - cx) / cx
      const dy = (y - cy) / cy
      const v = 1 - Math.max(0, dx * dx + dy * dy - 0.55) * 0.22
      const t = (BAYER[(y & 3) * 4 + (x & 3)] / 16 - 0.5) * 8
      // box-art punch: push each pixel's chroma away from its grey, then an S-curve
      const grey = (d[i] + d[i + 1] + d[i + 2]) / 3
      for (let c = 0; c < 3; c++) {
        const sat = grey + (d[i + c] - grey) * 1.18
        const n = Math.max(0, Math.min(1, sat / 255))
        const curved = (n + (n * n * (3 - 2 * n) - n) * 0.45) * 255
        const val = Math.max(0, Math.min(255, curved * v + t))
        d[i + c] = Math.round(val / 8) * 8 + (val >= 248 ? 7 : 0)
      }
      d[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
}

// Paint `recipe` into a 160x120 canvas context. `variant` shifts the camera a
// little for back-of-box screenshots so they are not copies of the cover.
// Back-of-box variants: 1 = closer camera, 2 = later hour, 3 = wide shot.
function variantRecipe(r, variant) {
  if (!variant) return r
  const v = JSON.parse(JSON.stringify(r))
  const lm = v.landmark
  if (variant === 1) {
    if (lm) { lm.scale = (lm.scale || 1) * 1.4; lm.x = Math.max(0.25, Math.min(0.75, (lm.x || 0.5) - 0.12)); lm.base = Math.min(0.9, (lm.base || 0.72) + 0.08) }
    v.horizon = Math.min(0.75, (v.horizon || 0.62) + 0.05)
  } else if (variant === 2) {
    v.sky = [mix(v.sky ? v.sky[0] : '#1d2a5c', '#05060f', 0.55), mix(v.sky ? v.sky[1] : '#f2b98a', '#2a2a5a', 0.6)]
    v.fog = mix(v.fog || v.sky[1], '#1a1a3a', 0.5)
    v.stars = Math.max(v.stars || 0, 40)
    if (v.sun) v.sun = Object.assign({}, v.sun, { x: 1 - v.sun.x, y: 0.2, r: Math.max(4, (v.sun.r || 8) * 0.6), colour: '#f2f0dc', glow: '#8fa3d6' })
    if (lm) lm.x = Math.max(0.2, Math.min(0.8, (lm.x || 0.5) + 0.16))
  } else {
    if (lm) { lm.scale = (lm.scale || 1) * 0.72; lm.base = Math.max(0.6, (lm.base || 0.72) - 0.04) }
    if (v.figure) v.figure = Object.assign({}, v.figure, { x: 0.5, base: Math.min(0.92, (v.figure.base || 0.78) + 0.08) })
    if (v.particles) v.particles = Object.assign({}, v.particles, { count: (v.particles.count || 20) * 2 })
  }
  return v
}

export function paintCover(ctx, recipe0, variant = 0) {
  const r = boxArtRecipe(variantRecipe(recipe0 || {}, variant))
  if (r.landmark) r.landmark = Object.assign({}, r.landmark, { scale: (r.landmark.scale || 1) * 1.3 })
  const rand = rng((r.seed || 'cover') + ':' + variant)
  const horizon = Math.round(COVER_H * (r.horizon || 0.62))
  const sky = r.sky || ['#1d2a5c', '#f2b98a']
  const fog = r.fog || sky[1]
  const g = ctx.createLinearGradient(0, 0, 0, horizon)
  g.addColorStop(0, sky[0])
  g.addColorStop(0.62, mix(sky[0], sky[1], 0.55))
  g.addColorStop(1, sky[1])
  ctx.fillStyle = g
  ctx.fillRect(0, 0, COVER_W, COVER_H)
  if (r.stars) {
    for (let i = 0; i < r.stars; i++) {
      const x = rand() * COVER_W
      const y = rand() * horizon * 0.7
      rect(ctx, x, y, 1, 1, alpha('#ffffff', 0.4 + rand() * 0.6))
      if (rand() > 0.93) { rect(ctx, x - 1, y, 3, 1, alpha('#ffffff', 0.5)); rect(ctx, x, y - 1, 1, 3, alpha('#ffffff', 0.5)) }
    }
  }
  if (r.aurora) aurora(ctx, r.aurora, rand)
  if (r.rays) {
    for (let i = 0; i < 5; i++) {
      const x = 20 + rand() * 120
      poly(ctx, [[x, 0], [x + 6, 0], [x + 26 + rand() * 10, horizon], [x + 10, horizon]], alpha(r.rays, 0.08 + rand() * 0.06))
    }
  }
  let sun = null
  if (r.sun) {
    sun = { x: r.sun.x * COVER_W, y: r.sun.y * COVER_H, colour: r.sun.colour || '#fff1c4' }
    glow(ctx, sun.x, sun.y, (r.sun.r || 8) * 4, r.sun.glow || sun.colour, 0.55)
    disc(ctx, sun.x, sun.y, r.sun.r || 8, sun.colour)
  }
  if (r.clouds) clouds(ctx, r.clouds, rand, horizon)
  const sunX = sun ? sun.x : COVER_W * 0.7
  const layers = Array.isArray(r.layers) ? r.layers : []
  layers.forEach((L0, idx) => {
    const L = Object.assign({}, L0)
    L.base = Math.round(COVER_H * (L0.base == null ? 0.62 : L0.base))
    L.height = COVER_H * (L0.height || 0.2)
    // box-art grade: less haze between layers, so silhouettes read at card size
    const fogT = 0.62 * (L0.fog == null ? Math.max(0, 0.55 - idx * 0.22) : L0.fog)
    if (L.kind === 'mountains') layerMountains(ctx, L, rand, sunX, fog, fogT)
    else if (L.kind === 'hills' || L.kind === 'dunes') layerHills(ctx, L, rand, sunX, fog, fogT)
    else if (L.kind === 'sea') layerSea(ctx, L, rand, sun, fog, fogT)
    else if (L.kind === 'pines') layerPines(ctx, L, rand, sunX, fog, fogT)
    else if (L.kind === 'mesas') layerMesas(ctx, L, rand, sunX, fog, fogT)
    else if (L.kind === 'cave') layerCave(ctx, L, rand, sunX, fog, fogT)
  })
  const groundTop = Math.round(COVER_H * (r.groundTop || 0.7))
  if (r.ground) ground(ctx, groundTop, r.ground, fog, rand, r.tiles !== false)
  if (r.landmark && LANDMARKS[r.landmark.kind]) {
    const m = Object.assign({}, r.landmark)
    const lb = Math.round(COVER_H * (m.base || 0.72))
    // a soft halo behind the hero landmark separates its silhouette from the sky
    glow(ctx, m.x * COVER_W, lb - 26 * (m.scale || 1), 46 * (m.scale || 1), shade(sky[1], 0.55), 0.5)
    LANDMARKS[m.kind](ctx, m, rand, lb)
  }
  if (r.figure) {
    // the hero figure at twice its old size, scaled about its feet (integer scale stays crisp)
    const fb = Math.round(COVER_H * (r.figure.base || 0.78))
    const fx = Math.round(r.figure.x * COVER_W)
    ctx.save()
    ctx.translate(fx, fb + 8)
    ctx.scale(2, 2)
    ctx.translate(-fx, -(fb + 8))
    figure(ctx, r.figure, fb)
    ctx.restore()
  }
  if (r.particles) particles(ctx, r.particles, rand)
  finish(ctx)
}

// Convenience for browsers: returns a canvas element with the painted cover.
export function coverCanvas(doc, recipe, variant = 0) {
  const c = doc.createElement('canvas')
  c.width = COVER_W
  c.height = COVER_H
  paintCover(c.getContext('2d'), recipe, variant)
  return c
}

// Style shelf art: the profile palette as a painted band scene.
export function styleRecipe(style) {
  const p = style.palette.length >= 4 ? style.palette : [style.colour, shade(style.colour, 0.3), shade(style.colour, -0.3), shade(style.colour, 0.6)]
  if (style.recipe) return style.recipe
  return {
    seed: 'style:' + style.id,
    sky: [shade(p[0], -0.2), p[Math.min(3, p.length - 1)]],
    fog: p[Math.min(3, p.length - 1)],
    sun: { x: 0.7, y: 0.32, r: 6, colour: shade(p[p.length - 1], 0.4) },
    layers: [
      { kind: 'mountains', colour: p[1], base: 0.6, height: 0.3 },
      { kind: 'hills', colour: p[2], base: 0.72, height: 0.12 }
    ],
    ground: p[0],
    groundTop: 0.72
  }
}
