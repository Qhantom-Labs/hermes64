// Catalogue model: normalisation, filters, grouping and plain-language labels.
// Pure functions only (no DOM), shared verbatim with desktop/plugin.js.

export const SCHEMA_ID = 'hermes64.studio.catalogue/1'

export const MODULES = [
  { id: 'story', label: 'STORY', colour: '#f2c14e' },
  { id: 'combat', label: 'COMBAT', colour: '#ff6b5e' },
  { id: 'region', label: 'REGION', colour: '#7ed67a' },
  { id: 'course', label: 'COURSE', colour: '#6fd3ff' }
]

export const VERDICTS = {
  SOLID: { label: 'SOLID', colour: '#5fd36a', ink: '#0d2412', rank: 0, words: 'Bot playtest found no blocking problems' },
  PLAYABLE: { label: 'PLAYABLE', colour: '#ffcf4a', ink: '#2d2205', rank: 1, words: 'Bot finished it, with rough spots' },
  ROUGH: { label: 'ROUGH', colour: '#ff9a3c', ink: '#2e1504', rank: 2, words: 'Bot hit stuck spots or droughts' },
  BROKEN: { label: 'BROKEN', colour: '#ff5a5a', ink: '#2f0707', rank: 3, words: 'Bot could not finish (crash, softlock or unreachable goal)' },
  UNTESTED: { label: 'UNTESTED', colour: 'transparent', ink: '#e9e4f5', rank: 4, words: 'No playtest report for this build yet' }
}

export const PROOF_WORDS = {
  proved: 'Every ending is reachable and no softlock exists (exhaustive story check)',
  rejected: 'The story check found an unreachable ending or a softlock',
  inconclusive: 'The story check hit its state cap before finishing',
  not_run: 'Story check not run on this build',
  stale: 'Last story check was for an older build'
}

export const FILTERS = [
  { id: 'all', label: 'ALL', icon: 'all' },
  { id: 'style', label: 'STYLE', icon: 'style' },
  { id: 'modules', label: 'MODULES', icon: 'modules' },
  { id: 'status', label: 'STATUS', icon: 'status' },
  { id: 'mine', label: 'MINE', icon: 'mine' }
]

const OWNER_RANK = { local: 0, bundled: 1, sample: 2 }
const HEX = /^#[0-9a-fA-F]{6}$/
const ID = /^[a-z0-9][a-z0-9_-]{0,63}$/

function str(v, max, fallback = '') {
  if (typeof v !== 'string') return fallback
  const clean = v.replace(/[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2066-\u2069]/g, ' ').replace(/\s+/g, ' ').trim()
  return clean.length > max ? clean.slice(0, max - 1) + '…' : clean
}

function colour(v, fallback) {
  return typeof v === 'string' && HEX.test(v) ? v.toLowerCase() : fallback
}

function oneOf(v, allowed, fallback) {
  return allowed.indexOf(v) >= 0 ? v : fallback
}

// The shelf's error line: the backend's own sentence when it already says what to do
// (it names the Settings field), else the reason plus the generic next step.
export function errorSentence(message) {
  const m = String(message == null ? '' : message).trim().replace(/[.\s]+$/, '')
  if (!m) return 'The shelf could not be read. Try again.'
  if (/\b(settings|choose|reopen|try again)\b/i.test(m)) return m + '.'
  return m + '. Check Projects root in Settings ▸ Plugins ▸ Hermes64 Studio, then try again.'
}

// A failed REST call (not an ok:false answer) means the plugin's backend routes are not
// there: hermes64's agent half is off, or Hermes has not restarted since it was enabled.
// Seen on the real Desktop as `404: {"detail":"Plugin not found"}`. Never blame the folder.
export function backendErrorSentence(err) {
  const m = String((err && err.message) || err || '').trim()
  if (/^40[34]\b|plugin not found/i.test(m)) {
    return 'The Hermes64 backend is off: switch on its Agent half in Capabilities ▸ Plugins (Hermes may need a restart), then try again.'
  }
  if (/timed? ?out/i.test(m)) return 'The Hermes64 backend did not answer in time. Try again.'
  return 'The Hermes64 backend could not be reached' + (m ? ' (' + m.slice(0, 80) + ')' : '') + '. Try again.'
}

// Normalise untrusted catalogue JSON into the exact shape the UI renders.
// Unknown fields are dropped; bad rows are reported, never guessed.
export function normaliseCatalogue(raw) {
  const out = { schema: SCHEMA_ID, source: 'unknown', games: [], styles: [], problems: [] }
  if (!raw || typeof raw !== 'object' || raw.schema !== SCHEMA_ID) {
    out.problems.push({ code: 'SCHEMA', detail: 'Not a Hermes64 Studio catalogue' })
    return out
  }
  out.source = oneOf(raw.source, ['projects_root', 'sample'], 'unknown')
  const seen = {}
  const styles = Array.isArray(raw.styles) ? raw.styles.slice(0, 256) : []
  for (const s of styles) {
    if (!s || typeof s !== 'object' || typeof s.id !== 'string' || !ID.test(s.id) || seen['s:' + s.id]) continue
    seen['s:' + s.id] = true
    out.styles.push({
      id: s.id,
      label: str(s.label, 40, s.id),
      colour: colour(s.colour, '#8a8fb8'),
      palette: (Array.isArray(s.palette) ? s.palette : []).filter(c => typeof c === 'string' && HEX.test(c)).slice(0, 8),
      status: oneOf(s.status, ['in_use', 'approved', 'example', 'draft_awaiting_approval', 'data_valid_runtime_pending'], 'data_valid_runtime_pending'),
      kind: oneOf(s.kind, ['profile', 'pack', 'draft'], 'profile'),
      note: str(s.note, 200),
      sample: s.sample === true,
      recipe: s.recipe && typeof s.recipe === 'object' ? s.recipe : null
    })
  }
  const games = Array.isArray(raw.games) ? raw.games.slice(0, 2000) : []
  for (const g of games) {
    if (!g || typeof g !== 'object' || typeof g.id !== 'string' || !ID.test(g.id) || seen['g:' + g.id]) {
      out.problems.push({ code: 'GAME_ROW', detail: 'Skipped a malformed game row' })
      continue
    }
    seen['g:' + g.id] = true
    const v = g.verification && typeof g.verification === 'object' ? g.verification : {}
    const pt = v.playtest && typeof v.playtest === 'object' ? v.playtest : {}
    const st = g.style && typeof g.style === 'object' ? g.style : {}
    const cover = g.cover && typeof g.cover === 'object' ? g.cover : {}
    out.games.push({
      id: g.id,
      title: str(g.title, 60, g.id),
      premise: str(g.premise, 280),
      sample: g.sample === true,
      owner: oneOf(g.owner, ['local', 'bundled', 'sample'], g.sample === true ? 'sample' : 'local'),
      style: {
        id: typeof st.id === 'string' && ID.test(st.id) ? st.id : 'unknown',
        label: str(st.label, 40, 'Unknown style'),
        colour: colour(st.colour, '#8a8fb8'),
        palette: (Array.isArray(st.palette) ? st.palette : []).filter(c => typeof c === 'string' && HEX.test(c)).slice(0, 8)
      },
      modules: MODULES.map(m => m.id).filter(id => Array.isArray(g.modules) && g.modules.indexOf(id) >= 0),
      rooms: Number.isInteger(g.rooms) && g.rooms >= 0 ? Math.min(g.rooms, 999) : null,
      endings: Number.isInteger(g.endings) && g.endings >= 0 ? Math.min(g.endings, 99) : null,
      verification: {
        proof: oneOf(v.proof && v.proof.status, ['proved', 'rejected', 'inconclusive', 'not_run', 'stale'], 'not_run'),
        replay: oneOf(v.replay && v.replay.status, ['passed', 'failed', 'not_run', 'stale'], 'not_run'),
        playtest: oneOf(pt.verdict, Object.keys(VERDICTS), 'UNTESTED'),
        playtestState: oneOf(pt.status, ['current', 'stale', 'none'], 'none'),
        playtestReasons: (Array.isArray(pt.reasons) ? pt.reasons : []).map(r => str(r, 120)).filter(Boolean).slice(0, 3),
        styleGate: oneOf(v.style_gate && v.style_gate.status, ['passed', 'failed', 'not_run'], 'not_run'),
        human: oneOf(v.human && v.human.status, ['not_yet', 'played'], 'not_yet')
      },
      exports: (Array.isArray(g.exports) ? g.exports : []).filter(e => e && typeof e === 'object')
        .map(e => ({ target: oneOf(e.target, ['web', 'macos', 'windows', 'share'], null), bytes: Number.isFinite(e.bytes) ? e.bytes : null, verified: e.verified === true }))
        .filter(e => e.target).slice(0, 8),
      cover: {
        // box: the cover tool's finished box art (logotype, band, corner mark already drawn)
        kind: oneOf(cover.kind, ['capture', 'file', 'procedural', 'box'], 'procedural'),
        src: typeof cover.src === 'string' ? cover.src : null,
        room: str(cover.room, 40),
        recipe: cover.recipe && typeof cover.recipe === 'object' ? cover.recipe : null,
        // Box-art composition hints (all optional): the crop that frames the subject,
        // the source size, which edge carries the title, and a colour grade.
        width: Number.isInteger(cover.width) && cover.width > 0 ? Math.min(cover.width, 4096) : null,
        height: Number.isInteger(cover.height) && cover.height > 0 ? Math.min(cover.height, 4096) : null,
        focus: Array.isArray(cover.focus) && cover.focus.length === 4 && cover.focus.every(n => Number.isInteger(n) && n >= 0 && n <= 4096) && cover.focus[2] > 0 && cover.focus[3] > 0 ? cover.focus.slice() : null,
        title: oneOf(cover.title, ['top', 'bottom'], 'top'),
        grade: normaliseGrade(cover.grade)
      },
      shots: (Array.isArray(g.shots) ? g.shots : []).filter(s => s && typeof s === 'object')
        .map(s => ({ src: typeof s.src === 'string' ? s.src : null, room: str(s.room, 40), recipe: s.recipe && typeof s.recipe === 'object' ? s.recipe : null }))
        .slice(0, 3),
      issues: (Array.isArray(g.issues) ? g.issues : []).filter(i => i && typeof i === 'object')
        .map(i => ({ code: str(i.code, 40, 'ISSUE'), detail: str(i.detail, 160) })).slice(0, 6)
    })
  }
  return out
}

const GRADE_LIMITS = { gamma: [0.4, 1.6], gain: [0.5, 2], lift: [-0.2, 0.3], saturation: [0, 2.5], warmth: [-0.3, 0.3], contrast: [0.5, 2] }
function normaliseGrade(raw) {
  if (!raw || typeof raw !== 'object') return null
  const out = {}
  for (const k of Object.keys(GRADE_LIMITS)) {
    const v = raw[k]
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = Math.max(GRADE_LIMITS[k][0], Math.min(GRADE_LIMITS[k][1], v))
  }
  if (['day', 'dusk', 'night'].indexOf(raw.mood) >= 0) out.mood = raw.mood
  return Object.keys(out).length ? out : null
}

// The four dots on a card, in order: story proof, bot play, style gate, human play.
// 'on' only when the check ran on this build and passed; 'fail' when it ran and
// failed; otherwise 'off'. A stale report never lights a dot.
export const DOTS = [
  { key: 'proof', label: 'PROOF' },
  { key: 'bot', label: 'BOT PLAY' },
  { key: 'style', label: 'STYLE GATE' },
  { key: 'human', label: 'HUMAN PLAY' }
]
export function verificationDots(game) {
  const v = game.verification
  const current = v.playtestState === 'current'
  return [
    v.proof === 'proved' ? 'on' : v.proof === 'rejected' ? 'fail' : 'off',
    !current || v.playtest === 'UNTESTED' ? 'off' : v.playtest === 'SOLID' || v.playtest === 'PLAYABLE' ? 'on' : 'fail',
    v.styleGate === 'passed' ? 'on' : v.styleGate === 'failed' ? 'fail' : 'off',
    v.human === 'played' ? 'on' : 'off'
  ]
}

// The grey badge: what kind of game this is, from its modules.
export function moduleBadge(game) {
  const extra = game.modules.filter(m => m !== 'story')
  if (extra.length === 0) return 'STORY'
  if (extra.length > 1) return 'MIXED'
  return { combat: 'COMBAT', region: 'EXPLORE', course: 'COURSE' }[extra[0]] || 'STORY'
}

function byOwnerThenTitle(a, b) {
  const r = (OWNER_RANK[a.owner] || 0) - (OWNER_RANK[b.owner] || 0)
  if (r) return r
  const t = a.title.localeCompare(b.title, 'en', { sensitivity: 'base' })
  return t || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

function moduleGroup(g) {
  const extra = g.modules.filter(m => m !== 'story')
  if (extra.length === 0) return { key: '0', label: 'STORY' }
  if (extra.length > 1) return { key: '4', label: 'MIXED' }
  const idx = ['combat', 'region', 'course'].indexOf(extra[0]) + 1
  return { key: String(idx), label: extra[0].toUpperCase() }
}

// The ordered, grouped shelf for one filter. NEW GAME leads every game shelf.
export function gameShelf(catalogue, filterId) {
  let games = catalogue.games.slice()
  let groupOf = () => null
  if (filterId === 'mine') games = games.filter(g => g.owner === 'local')
  if (filterId === 'style') groupOf = g => ({ key: g.style.label.toLowerCase() + '|' + g.style.id, label: g.style.label.toUpperCase() })
  if (filterId === 'modules') groupOf = moduleGroup
  if (filterId === 'status') {
    groupOf = g => {
      const v = VERDICTS[g.verification.playtest]
      return { key: String(v.rank), label: v.label }
    }
  }
  games.sort((a, b) => {
    const ga = groupOf(a)
    const gb = groupOf(b)
    if (ga && gb && ga.key !== gb.key) return ga.key < gb.key ? -1 : 1
    return byOwnerThenTitle(a, b)
  })
  const items = [{ type: 'new', id: '__new__', group: null }]
  for (const g of games) {
    const grp = groupOf(g)
    items.push({ type: 'game', id: g.id, game: g, group: grp ? grp.label : null })
  }
  return items
}

const STYLE_RANK = { draft_awaiting_approval: 0, approved: 1, example: 2, data_valid_runtime_pending: 3 }

export function styleShelf(catalogue) {
  const counts = {}
  for (const g of catalogue.games) counts[g.style.id] = (counts[g.style.id] || 0) + 1
  return catalogue.styles.slice()
    .sort((a, b) => (STYLE_RANK[a.status] - STYLE_RANK[b.status]) || a.label.localeCompare(b.label, 'en', { sensitivity: 'base' }))
    .map(s => ({ type: 'style', id: s.id, style: s, games: counts[s.id] || 0, group: null }))
}

export const STYLE_STATUS_WORDS = {
  in_use: 'Used by a game in this folder (looks are checked per game, not approved here)',
  draft_awaiting_approval: 'Draft from references, waiting for your approval',
  approved: 'Approved style',
  example: 'Example profile (data only, no rendered approval)',
  data_valid_runtime_pending: 'Valid data; runtime support still pending'
}

export function counterText(filterLabel, items, index) {
  const games = items.filter(i => i.type !== 'new').length
  const item = items[index]
  if (!item || item.type === 'new') return { head: filterLabel, pos: String(games) }
  const pos = items.slice(0, index + 1).filter(i => i.type !== 'new').length
  return { head: item.group ? filterLabel + ' · ' + item.group : filterLabel, pos: pos + '/' + games }
}

export function hasExport(game, target) {
  return game.exports.some(e => e.target === target)
}

export function humanBytes(n) {
  if (!Number.isFinite(n)) return ''
  if (n < 1024) return n + ' B'
  if (n < 1048576) return (n / 1024).toFixed(0) + ' KB'
  return (n / 1048576).toFixed(1) + ' MB'
}

// Plain, honest one-line verification rows for the detail view.
export function verificationRows(game) {
  const v = game.verification
  const rows = []
  rows.push({ key: 'proof', icon: 'key', label: 'PROOF', value: v.proof === 'proved' ? 'PROVED' : v.proof === 'not_run' ? 'NOT RUN' : v.proof.toUpperCase(), tone: v.proof === 'proved' ? 'good' : v.proof === 'rejected' ? 'bad' : 'none', words: PROOF_WORDS[v.proof] })
  const verdict = VERDICTS[v.playtest]
  rows.push({ key: 'playtest', icon: 'bot', label: 'BOT PLAY', value: verdict.label + (v.playtestState === 'stale' ? ' · OLD' : ''), tone: v.playtest === 'SOLID' ? 'good' : v.playtest === 'UNTESTED' ? 'none' : v.playtest === 'PLAYABLE' ? 'warn' : 'bad', words: verdict.words + (v.playtestState === 'stale' ? ' (report is for an older build)' : '') })
  rows.push({ key: 'style', icon: 'chips', label: 'STYLE GATE', value: v.styleGate === 'not_run' ? 'NOT RUN' : v.styleGate.toUpperCase(), tone: v.styleGate === 'passed' ? 'good' : v.styleGate === 'failed' ? 'bad' : 'none', words: v.styleGate === 'passed' ? 'Measured look checks passed (not human art approval)' : v.styleGate === 'failed' ? 'Measured look checks failed on at least one room' : 'Look checks not run' })
  rows.push({ key: 'human', icon: 'person', label: 'HUMAN PLAY', value: v.human === 'played' ? 'PLAYED' : 'NOT YET', tone: v.human === 'played' ? 'good' : 'none', words: v.human === 'played' ? 'A person has played this build' : 'Nobody has marked this build as played by a person' })
  return rows
}
