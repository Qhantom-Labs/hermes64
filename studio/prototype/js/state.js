// The Studio state machine: one pure reducer shared by the prototype and the
// desktop plugin. It never touches the DOM or the host; it returns effects
// (sounds, hand-offs, play requests) for the shell to carry out.
import { FILTERS, gameShelf, styleShelf, hasExport } from './model.js'

export const SOUND = {
  move: 'ui.move',
  select: 'ui.select',
  back: 'ui.back',
  filter: 'core.ui.move.02',
  shelf: 'core.hatch.slide.open',
  insert: 'hatch.open',
  boot: 'core.machine.computer.accept',
  newgame: 'core.magic.chime',
  handoff: 'core.ui.confirm.01',
  bump: 'core.ui.error.01'
}

// The icon bar above the shelf, left to right.
export const NAV = [
  { id: 'games', label: 'Games' },
  { id: 'styles', label: 'Styles' },
  { id: 'filters', label: 'Filters' },
  { id: 'help', label: 'Help' }
]

export function initialState(opts = {}) {
  return {
    view: 'home',
    bar: null,
    help: false,
    shelf: opts.shelf === 'styles' ? 'styles' : 'games',
    filter: FILTERS.some(f => f.id === opts.filter) ? opts.filter : 'all',
    sel: { games: opts.sel || null, styles: opts.styleSel || null },
    menu: 0,
    confirm: null,
    newgame: { text: '', style: 0 },
    jump: null,
    input: opts.input === 'pad' ? 'pad' : 'keys',
    playing: null,
    notice: null,
    tick: 0
  }
}

export function shelfItems(cat, state) {
  return state.shelf === 'styles' ? styleShelf(cat) : gameShelf(cat, state.filter)
}

export function selectedIndex(items, state) {
  const id = state.sel[state.shelf]
  const i = items.findIndex(it => it.id === id)
  if (i >= 0) return i
  if (state.shelf === 'games') return items.length > 1 ? 1 : 0
  return 0
}

export function newGameStyles(cat) {
  return cat.styles.filter(s => s.status !== 'draft_awaiting_approval')
}

export function detailMenu(item, caps = {}) {
  if (!item) return []
  if (item.type === 'style') {
    const draft = item.style.status === 'draft_awaiting_approval'
    return [
      { id: 'style_new', label: 'NEW GAME IN THIS STYLE', enabled: !draft, reason: draft ? 'Approve the draft before building with it' : '' },
      { id: 'style_review', label: draft ? 'REVIEW WITH HERMES' : 'ASK HERMES ABOUT IT', enabled: true, reason: '' }
    ]
  }
  if (item.type !== 'game') return []
  const g = item.game
  const web = hasExport(g, 'web')
  const mac = hasExport(g, 'macos')
  return [
    { id: 'play', label: web || !mac ? 'PLAY' : 'PLAY MACOS BUILD', tag: web ? 'WEB' : mac ? 'MACOS' : 'NO BUILD', enabled: web || mac, native: !web && mac, reason: web || mac ? '' : 'No web export yet. Export first.' },
    { id: 'edit', label: 'EDIT WITH HERMES', enabled: true, reason: '' },
    { id: 'export', label: 'EXPORT', tag: g.sample ? 'SAMPLE' : '', enabled: !g.sample, reason: g.sample ? 'Sample entry: nothing to export' : '' },
    { id: 'folder', label: 'OPEN FOLDER', tag: g.sample ? 'SAMPLE' : caps.reveal === false ? 'REMOTE' : '', enabled: !g.sample && caps.reveal !== false, reason: g.sample ? 'Sample entry: no project folder' : caps.reveal === false ? 'Folder is on another machine' : '' }
  ]
}

function handoffText(kind, ctx) {
  if (kind === 'new') {
    return 'Let\'s make a new Hermes64 game.\nPremise: ' + (ctx.text || '(none yet: help me choose one, asking one question at a time)') +
      (ctx.style ? '\nStyle: ' + ctx.style.label + ' (' + ctx.style.id + ')' : '') +
      '\nScaffold it with hermes64_scaffold, then compile and check before building assets.'
  }
  if (kind === 'edit') return 'Open the Hermes64 project "' + ctx.title + '" (' + ctx.id + ') and help me edit it. Re-run hermes64_check after every change.'
  if (kind === 'export') return 'Export the Hermes64 project "' + ctx.title + '" (' + ctx.id + ') as a local web build. Show me what will be written before running it.'
  if (kind === 'style_review') return 'Review the Hermes64 style "' + ctx.label + '" (' + ctx.id + ') with me. Nothing is approved until I say so.'
  return ''
}

export function firstEnabled(menu) {
  const i = menu.findIndex(m => m.enabled)
  return i < 0 ? 0 : i
}

function withSel(state, items, index) {
  const i = Math.max(0, Math.min(items.length - 1, index))
  const sel = Object.assign({}, state.sel)
  sel[state.shelf] = items[i] ? items[i].id : null
  return Object.assign({}, state, { sel })
}

// Icon bar: Games and Styles switch shelves (and hand the cursor back to the
// shelf); Filters steps to the next filter and keeps the cursor; Help opens the
// controls card.
function activateNav(state, id, cat, caps, fx) {
  const at = NAV.findIndex(n => n.id === id)
  if (at < 0) return { state, effects: fx }
  if (id === 'help') return { state: Object.assign({}, state, { help: true, bar: state.bar == null ? null : at }), effects: [{ type: 'sound', id: SOUND.select }] }
  if (id === 'filters') {
    const base = state.shelf === 'games' ? state : Object.assign({}, state, { shelf: 'games' })
    const r = reduce(Object.assign({}, base, { bar: null }), { type: 'filter', dir: 1 }, cat, caps)
    if (base !== state) r.effects.push({ type: 'reshelf', dir: -1 })
    return { state: Object.assign({}, r.state, { bar: state.bar == null ? null : at }), effects: r.effects }
  }
  const target = id === 'styles' ? 'styles' : 'games'
  if (target === 'styles' && !cat.styles.length) return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
  if (target === state.shelf) return { state: Object.assign({}, state, { bar: null }), effects: [{ type: 'sound', id: SOUND.select }] }
  return { state: Object.assign({}, state, { shelf: target, bar: null, notice: null }), effects: [{ type: 'sound', id: SOUND.shelf }, { type: 'reshelf', dir: target === 'styles' ? 1 : -1 }] }
}

// reduce(state, action, catalogue, caps) -> { state, effects }
export function reduce(state, action, cat, caps = {}) {
  const fx = []
  const items = shelfItems(cat, state)
  const index = selectedIndex(items, state)
  const item = items[index]
  let next = state
  const t = action.type

  if (t === 'input') return { state: state.input === action.mode ? state : Object.assign({}, state, { input: action.mode }), effects: fx }
  if (t === 'tick') return { state: Object.assign({}, state, { tick: state.tick + 1 }), effects: fx }

  if (state.help) {
    if (t === 'back' || t === 'open' || (t === 'nav' && action.id === 'help')) return { state: Object.assign({}, state, { help: false }), effects: [{ type: 'sound', id: SOUND.back }] }
    return { state, effects: fx }
  }

  if (state.view === 'play') {
    if (t === 'back' || t === 'eject') {
      fx.push({ type: 'sound', id: SOUND.back }, { type: 'eject' })
      next = Object.assign({}, state, { view: 'detail', playing: null })
    }
    return { state: next, effects: fx }
  }

  if (state.jump) {
    if (t === 'text') {
      const q = String(action.value || '').slice(0, 40)
      const ql = q.toLowerCase()
      let found = ql ? items.findIndex(it => it.game && it.game.title.toLowerCase().startsWith(ql)) : -1
      if (found < 0 && ql) found = items.findIndex(it => it.game && it.game.title.toLowerCase().indexOf(ql) >= 0)
      const miss = !!ql && found < 0
      next = Object.assign({}, state, { jump: Object.assign({}, state.jump, { text: q, miss }) })
      if (miss && !state.jump.miss) fx.push({ type: 'sound', id: SOUND.bump })
      if (found >= 0) next = withSel(next, items, found)
      return { state: next, effects: fx }
    }
    if (t === 'open') return { state: Object.assign({}, state, { jump: null }), effects: [{ type: 'sound', id: SOUND.select }] }
    if (t === 'back') {
      const restored = Object.assign({}, state.sel)
      restored[state.shelf] = state.jump.restore
      return { state: Object.assign({}, state, { jump: null, sel: restored }), effects: [{ type: 'sound', id: SOUND.back }] }
    }
    return { state, effects: fx }
  }

  if (state.view === 'newgame') {
    const styles = newGameStyles(cat)
    if (t === 'text') return { state: Object.assign({}, state, { newgame: Object.assign({}, state.newgame, { text: String(action.value || '').slice(0, 280) }) }), effects: fx }
    if (t === 'move' && styles.length) {
      const s = (state.newgame.style + action.dx + styles.length) % styles.length
      fx.push({ type: 'sound', id: SOUND.move })
      return { state: Object.assign({}, state, { newgame: Object.assign({}, state.newgame, { style: s }) }), effects: fx }
    }
    if (t === 'open') {
      const style = styles[state.newgame.style] || null
      fx.push({ type: 'sound', id: SOUND.handoff }, { type: 'handoff', kind: 'new', text: handoffText('new', { text: state.newgame.text.trim(), style }) })
      next = Object.assign({}, state, { view: 'home', newgame: { text: '', style: 0 }, notice: { text: 'HANDED TO HERMES', tone: 'good' } })
      return { state: next, effects: fx }
    }
    if (t === 'back') return { state: Object.assign({}, state, { view: 'home' }), effects: [{ type: 'sound', id: SOUND.back }] }
    return { state, effects: fx }
  }

  if (state.view === 'detail') {
    const menu = detailMenu(item, caps)
    if (state.confirm) {
      if (t === 'move' || t === 'vertical') return { state: Object.assign({}, state, { confirm: Object.assign({}, state.confirm, { yes: !state.confirm.yes }) }), effects: [{ type: 'sound', id: SOUND.move }] }
      if (t === 'open') {
        if (state.confirm.yes) {
          fx.push({ type: 'sound', id: SOUND.insert }, { type: 'play', id: item.id, target: 'macos' })
          return { state: Object.assign({}, state, { confirm: null }), effects: fx }
        }
        return { state: Object.assign({}, state, { confirm: null }), effects: [{ type: 'sound', id: SOUND.back }] }
      }
      if (t === 'back') return { state: Object.assign({}, state, { confirm: null }), effects: [{ type: 'sound', id: SOUND.back }] }
      return { state, effects: fx }
    }
    if (t === 'vertical') {
      const m = Math.max(0, Math.min(menu.length - 1, state.menu + action.dy))
      if (m !== state.menu) fx.push({ type: 'sound', id: SOUND.move })
      return { state: Object.assign({}, state, { menu: m }), effects: fx }
    }
    if (t === 'menu_set') return { state: Object.assign({}, state, { menu: Math.max(0, Math.min(menu.length - 1, action.index)) }), effects: fx }
    if (t === 'move') {
      let j = index + action.dx
      while (items[j] && items[j].type === 'new') j += action.dx
      if (!items[j]) return { state, effects: [{ type: 'sound', id: SOUND.bump }, { type: 'bump', dir: action.dx }] }
      fx.push({ type: 'sound', id: SOUND.move })
      return { state: Object.assign(withSel(state, items, j), { menu: firstEnabled(detailMenu(items[j], caps)), notice: null }), effects: fx }
    }
    if (t === 'open') {
      const entry = menu[state.menu]
      if (!entry || !entry.enabled) return { state: Object.assign({}, state, { notice: entry ? { text: entry.reason, tone: 'warn' } : null }), effects: [{ type: 'sound', id: SOUND.bump }] }
      if (entry.id === 'play') {
        if (entry.native) return { state: Object.assign({}, state, { confirm: { kind: 'native', yes: false } }), effects: [{ type: 'sound', id: SOUND.select }] }
        fx.push({ type: 'sound', id: SOUND.insert }, { type: 'play', id: item.id, target: 'web' })
        return { state: Object.assign({}, state, { view: 'play', playing: { id: item.id, target: 'web' } }), effects: fx }
      }
      if (entry.id === 'edit' || entry.id === 'export') {
        fx.push({ type: 'sound', id: SOUND.handoff }, { type: 'handoff', kind: entry.id, id: item.id, text: handoffText(entry.id, { id: item.id, title: item.game.title }) })
        return { state: Object.assign({}, state, { notice: { text: 'HANDED TO HERMES', tone: 'good' } }), effects: fx }
      }
      if (entry.id === 'folder') {
        fx.push({ type: 'sound', id: SOUND.select }, { type: 'reveal', id: item.id })
        return { state, effects: fx }
      }
      if (entry.id === 'style_new') {
        const styles = newGameStyles(cat)
        const s = Math.max(0, styles.findIndex(x => x.id === item.id))
        fx.push({ type: 'sound', id: SOUND.newgame })
        return { state: Object.assign({}, state, { view: 'newgame', shelf: 'games', newgame: { text: '', style: s } }), effects: fx }
      }
      if (entry.id === 'style_review') {
        fx.push({ type: 'sound', id: SOUND.handoff }, { type: 'handoff', kind: 'style_review', id: item.id, text: handoffText('style_review', { id: item.id, label: item.style.label }) })
        return { state: Object.assign({}, state, { notice: { text: 'HANDED TO HERMES', tone: 'good' } }), effects: fx }
      }
    }
    if (t === 'back') return { state: Object.assign({}, state, { view: 'home', notice: null }), effects: [{ type: 'sound', id: SOUND.back }] }
    return { state, effects: fx }
  }

  // view === 'home'
  if (t === 'nav') return activateNav(state, action.id, cat, caps, fx)
  // Pointer and jump actions hand the cursor back to the shelf first.
  if (state.bar != null && (t === 'select_id' || t === 'page' || t === 'edge' || t === 'jump_open')) state = Object.assign({}, state, { bar: null })
  if (state.bar != null) {
    if (t === 'move') {
      const b = state.bar + action.dx
      if (b < 0 || b >= NAV.length) return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
      return { state: Object.assign({}, state, { bar: b }), effects: [{ type: 'sound', id: SOUND.move }] }
    }
    if (t === 'open') return activateNav(state, NAV[state.bar].id, cat, caps, fx)
    if (t === 'back' || t === 'menu' || (t === 'vertical' && action.dy > 0)) return { state: Object.assign({}, state, { bar: null }), effects: [{ type: 'sound', id: SOUND.back }] }
    if (t === 'vertical') return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
    if (t !== 'filter') return { state, effects: fx }
  }
  if (t === 'menu' || (t === 'vertical' && action.dy < 0)) {
    return { state: Object.assign({}, state, { bar: state.shelf === 'styles' ? 1 : 0, notice: null }), effects: [{ type: 'sound', id: SOUND.select }] }
  }
  if (t === 'move' || t === 'page' || t === 'edge') {
    let j = index
    if (t === 'move') j = index + action.dx
    if (t === 'page') j = index + action.dx * (items.length > 100 ? 10 : 5)
    if (t === 'edge') j = action.to === 'first' ? 0 : items.length - 1
    j = Math.max(0, Math.min(items.length - 1, j))
    if (j === index) return { state, effects: [{ type: 'sound', id: SOUND.bump }, { type: 'bump', dir: action.dx || (action.to === 'first' ? -1 : 1) }] }
    fx.push({ type: 'sound', id: SOUND.move })
    return { state: Object.assign(withSel(state, items, j), { notice: null }), effects: fx }
  }
  if (t === 'select_id') {
    const j = items.findIndex(it => it.id === action.id)
    if (j < 0) return { state, effects: fx }
    if (j === index) return reduce(state, { type: 'open' }, cat, caps)
    fx.push({ type: 'sound', id: SOUND.move })
    return { state: withSel(state, items, j), effects: fx }
  }
  if (t === 'filter') {
    if (state.shelf !== 'games') return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
    const k = FILTERS.findIndex(f => f.id === state.filter)
    const f = FILTERS[(k + action.dir + FILTERS.length) % FILTERS.length].id
    next = Object.assign({}, state, { filter: f, notice: null })
    const nitems = shelfItems(cat, next)
    if (!nitems.some(it => it.id === state.sel.games)) next = withSel(next, nitems, nitems.length > 1 ? 1 : 0)
    fx.push({ type: 'sound', id: SOUND.filter }, { type: 'refilter' })
    return { state: next, effects: fx }
  }
  if (t === 'filter_set') {
    if (state.shelf !== 'games' || state.filter === action.id) return { state, effects: fx }
    const k = FILTERS.findIndex(f => f.id === action.id)
    if (k < 0) return { state, effects: fx }
    const cur = FILTERS.findIndex(f => f.id === state.filter)
    return reduce(state, { type: 'filter', dir: k - cur }, cat, caps)
  }
  if (t === 'vertical') return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
  if (t === 'shelf') {
    const dir = action.dir
    const target = dir > 0 ? 'styles' : 'games'
    if (target === state.shelf || (target === 'styles' && !cat.styles.length)) return { state, effects: [{ type: 'sound', id: SOUND.bump }] }
    fx.push({ type: 'sound', id: SOUND.shelf }, { type: 'reshelf', dir })
    return { state: Object.assign({}, state, { shelf: target, notice: null }), effects: fx }
  }
  if (t === 'open') {
    if (!item) return { state, effects: fx }
    if (item.type === 'new') {
      fx.push({ type: 'sound', id: SOUND.newgame })
      return { state: Object.assign({}, state, { view: 'newgame', newgame: { text: '', style: 0 } }), effects: fx }
    }
    fx.push({ type: 'sound', id: SOUND.select })
    return { state: Object.assign({}, state, { view: 'detail', menu: firstEnabled(detailMenu(item, caps)), notice: null }), effects: fx }
  }
  if (t === 'jump_open') {
    if (state.shelf !== 'games') return { state, effects: fx }
    return { state: Object.assign({}, state, { jump: { text: '', miss: false, restore: state.sel.games } }), effects: [{ type: 'sound', id: SOUND.select }] }
  }
  if (t === 'back') {
    if (state.shelf === 'styles') return reduce(state, { type: 'shelf', dir: -1 }, cat, caps)
    return { state: Object.assign({}, state, { notice: null }), effects: fx }
  }
  return { state, effects: fx }
}
