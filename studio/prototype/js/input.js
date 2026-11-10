// Input mapping: keyboard events and W3C "standard" gamepads become the same
// abstract actions. The pad reader is pure apart from the snapshot it is given,
// so tests can feed it fake pads.

export function keyAction(e, view) {
  const k = e.key
  const typing = view === 'newgame' || view === 'jump'
  if (typing) {
    if (k === 'Enter') return { type: 'open' }
    if (k === 'Escape') return { type: 'back' }
    if (view === 'newgame' && (k === 'ArrowUp' || k === 'ArrowDown')) return { type: 'move', dx: k === 'ArrowUp' ? -1 : 1 }
    return null
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return null
  // Tab opens the icon bar; a second Tab (or Shift+Tab) is left to the browser so
  // keyboard focus can always leave the Studio.
  if (k === 'Tab') return e.shiftKey || view === 'bar' || view !== 'home' ? null : { type: 'menu' }
  switch (k) {
    // Shift+arrows page the shelf. PageUp/PageDown also page in a plain browser, but
    // inside Hermes Desktop the host owns them (conversation.scrollPageUp/Down).
    case 'ArrowLeft': return e.shiftKey ? { type: 'page', dx: -1 } : { type: 'move', dx: -1 }
    case 'ArrowRight': return e.shiftKey ? { type: 'page', dx: 1 } : { type: 'move', dx: 1 }
    case 'ArrowUp': return { type: 'vertical', dy: -1 }
    case 'ArrowDown': return { type: 'vertical', dy: 1 }
    case 'Enter':
    case ' ': return { type: 'open' }
    case 'Escape':
    case 'Backspace': return { type: 'back' }
    case 'q': case 'Q': case '[': return { type: 'filter', dir: -1 }
    case 'e': case 'E': case ']': return { type: 'filter', dir: 1 }
    case 'PageUp': return { type: 'page', dx: -1 }
    case 'PageDown': return { type: 'page', dx: 1 }
    case 'Home': return { type: 'edge', to: 'first' }
    case 'End': return { type: 'edge', to: 'last' }
    case '/': return { type: 'jump_open' }
    case 'm': case 'M': return { type: 'toggle_sound' }
    case '?': return { type: 'nav', id: 'help' }
    default: return null
  }
}

// Standard mapping: 0 A, 1 B, 4 LB, 5 RB, 6 LT, 7 RT, 12-15 d-pad U/D/L/R.
const BUTTONS = [
  [0, { type: 'open' }],
  [1, { type: 'back' }],
  [4, { type: 'filter', dir: -1 }],
  [5, { type: 'filter', dir: 1 }],
  [6, { type: 'page', dx: -1 }],
  [7, { type: 'page', dx: 1 }],
  [9, { type: 'menu' }]
]
const DIRS = [
  ['left', 14, a => a[0] < -0.55, { type: 'move', dx: -1 }],
  ['right', 15, a => a[0] > 0.55, { type: 'move', dx: 1 }],
  ['up', 12, a => a[1] < -0.55, { type: 'vertical', dy: -1 }],
  ['down', 13, a => a[1] > 0.55, { type: 'vertical', dy: 1 }]
]

export class PadReader {
  constructor(opts = {}) {
    this.delay = opts.delay || 360
    this.repeat = opts.repeat || 110
    this.fastest = opts.fastest || 60
    this.prev = {}
    this.held = {}
  }

  // pads: array-like from navigator.getGamepads(); returns actions this frame.
  poll(pads, now, view) {
    const out = []
    const pad = Array.from(pads || []).find(p => p && p.connected !== false && p.buttons && p.buttons.length)
    if (!pad) {
      this.prev = {}
      this.held = {}
      return out
    }
    const pressed = i => !!(pad.buttons[i] && (pad.buttons[i].pressed || pad.buttons[i].value > 0.5))
    const axes = pad.axes || [0, 0]
    for (const [i, action] of BUTTONS) {
      const now1 = pressed(i)
      if (now1 && !this.prev['b' + i]) out.push(Object.assign({}, action))
      this.prev['b' + i] = now1
    }
    for (const [name, btn, axis, action0] of DIRS) {
      const action = view === 'newgame' && (name === 'left' || name === 'right') ? { type: 'move', dx: name === 'left' ? -1 : 1 } : action0
      const down = pressed(btn) || axis(axes)
      const h = this.held[name]
      if (down && !h) {
        out.push(Object.assign({}, action))
        this.held[name] = { since: now, last: now, count: 0 }
      } else if (down && h) {
        const interval = Math.max(this.fastest, this.repeat - h.count * 6)
        if (now - h.since >= this.delay && now - h.last >= interval) {
          out.push(Object.assign({}, action, { repeat: true }))
          h.last = now
          h.count++
        }
      } else if (!down && h) {
        delete this.held[name]
      }
    }
    if (out.length) out.unshift({ type: 'input', mode: 'pad' })
    return out
  }
}
