// ---- desktop glue: studio/plugin/glue.js (hand-written; the rest of this file is generated) ----
// Registers the Studio three ways: a tab beside Sessions and Bots (a narrow cartridge
// rack), a sidebar nav row, and the full-page route that runs the same Studio shell
// as the prototype. Every host-specific action goes through the SDK: ctx.rest to this
// plugin's own backend, host.composer for the chat hand-off, SandboxedFrame for web
// builds, ctx.os.revealPath for folders. Nothing runs on load except registration.

const STUDIO_PATH = '/hermes64-studio'
// The page and the rack live in this one module, so a tiny store keeps their
// selections in step (the rack highlights whatever the page has selected).
const selection = { id: null, listeners: new Set() }
function setSelection(id) {
  selection.id = id
  for (const fn of selection.listeners) { try { fn(id) } catch (err) { /* a closed view */ } }
}
// The mounted page (route views unmount when the user navigates away), so the rack can
// steer an already-open page instead of waiting for a remount that never comes.
const page = { api: null, el: null }
const PLAY_URL = /^http:\/\/127\.0\.0\.1:\d{2,5}\/[A-Za-z0-9_-]{16,64}\/[A-Za-z0-9_.-]+$/

function studioHost(ctx, hooks) {
  const images = {}
  const rest = (path, opts) => ctx.rest(path, Object.assign({ timeoutMs: 20000 }, opts || {}))
  return {
    caps: { reveal: true },
    async loadCatalogue() {
      let r
      try {
        r = await rest('/studio/catalogue')
      } catch (err) {
        throw new Error(backendErrorSentence(err))
      }
      if (!r || r.ok !== true) throw new Error((r && r.message) || backendErrorSentence(''))
      // A Windows backend says so; the detail menu then offers PLAY WINDOWS BUILD (macOS backends say nothing).
      if (r.native_launch === 'windows') this.caps.nativeTarget = 'windows'
      return r.catalogue
    },
    async image(src) {
      if (typeof src !== 'string' || !/^cover\/[a-z][a-z0-9_-]{0,63}\/[0-3]\/[0-9a-f]{12}$/.test(src)) return null
      if (images[src]) return images[src]
      const r = await rest('/studio/' + src)
      if (r && r.ok && typeof r.data_url === 'string' && r.data_url.startsWith('data:image/png;base64,')) images[src] = r.data_url
      return images[src] || null
    },
    async soundUrl(id) {
      const r = await rest('/studio/sound/' + encodeURIComponent(id))
      return r && r.ok && typeof r.data_url === 'string' && r.data_url.startsWith('data:audio/wav;base64,') ? r.data_url : null
    },
    async handoff(e) {
      // A fresh chat with the brief written into its composer. The user reads it and
      // presses Enter themselves; the Studio never sends on their behalf.
      host.newChat()
      for (let i = 0; i < 24; i++) {
        await new Promise(resolve => ctx.setTimeout(resolve, 125))
        if (await host.composer.setDraft('new', e.text)) {
          host.composer.focus('new')
          return { ok: true }
        }
      }
      const copied = await ctx.os.writeClipboard(e.text)
      host.notify({ kind: 'info', message: copied ? 'Studio brief copied: paste it into the new chat.' : 'Open a new chat to continue in Hermes.' })
      return { ok: true }
    },
    async play(e) {
      const r = await rest('/studio/play', { method: 'POST', body: { game: e.id, target: 'web' } })
      if (r && r.ok && typeof r.url === 'string' && PLAY_URL.test(r.url)) return { url: r.url }
      return { message: (r && r.message) || 'Could not start the web build' }
    },
    showFrame(f) { hooks.setFrame(f) },
    hideFrame() { hooks.setFrame(null) },
    eject() { return rest('/studio/stop', { method: 'POST', body: {} }).catch(() => null) },
    async launchNative(e) {
      const r = await rest('/studio/launch', { method: 'POST', body: { game: e.id, target: e.target === 'windows' ? 'windows' : 'macos' } })
      return r && r.ok ? { ok: true } : { ok: false, message: (r && r.message) || 'Could not open the build' }
    },
    async reveal(id) {
      const r = await rest('/studio/folder/' + encodeURIComponent(id))
      if (!r || !r.ok || typeof r.path !== 'string') return { ok: false, message: (r && r.message) || 'Folder unavailable' }
      return { ok: await ctx.os.revealPath(r.path) }
    },
    openStudio(opts) {
      const id = opts && opts.sel ? String(opts.sel).slice(0, 64) : null
      const live = page.api && page.el && page.el.isConnected ? page : null
      if (!live) ctx.storage.set('focus', id)
      // navigate() also fronts the workspace pane when the route is already current.
      host.navigate(STUDIO_PATH)
      if (live) {
        if (id && live.api.state().view === 'home') live.api.dispatch({ type: 'select_id', id })
        live.el.focus()
      }
    }
  }
}

function StudioPage(props) {
  const ctx = props.ctx
  const ref = useRef(null)
  const [frame, setFrame] = useState(null)
  const [epoch, setEpoch] = useState(0)
  useEffect(() => {
    if (!ref.current) return undefined
    // The Studio owns a child element React never renders, so re-renders (for the
    // play frame) can never touch the classes and DOM the Studio manages.
    const el = document.createElement('div')
    el.style.cssText = 'position:absolute;inset:0'
    ref.current.appendChild(el)
    let gone = false
    let api = null
    const hostApi = studioHost(ctx, { setFrame: f => { if (!gone) setFrame(f) } })
    hostApi.reload = () => { if (!gone) setEpoch(n => n + 1) }
    // The game frame is rendered by React beside the Studio (SandboxedFrame); the bridge's
    // eject message counts only when it comes from that exact frame.
    hostApi.isFrameSource = source => {
      const hostEl = ref.current && ref.current.parentElement
      const f = hostEl && hostEl.querySelector('.h64s-frame-layer iframe')
      return !!f && f.contentWindow === source
    }
    hostApi.onSelect = id => setSelection(id)
    const focus = ctx.storage.get('focus', null)
    ctx.storage.remove('focus')
    const params = focus ? { sel: focus } : {}
    if (props.params) Object.assign(params, props.params)
    boot(el, { host: hostApi, useLocation: false, debug: !!props.debug, params })
      .then(a => { if (gone) { a.dispose(); return } api = a; page.api = a; page.el = el })
      .catch(err => host.notifyError(err, 'The Studio could not start'))
    return () => {
      gone = true
      if (page.el === el) { page.api = null; page.el = null }
      if (api) api.dispose()
      el.remove()
      hostApi.eject()
    }
  }, [epoch])
  const children = [
    jsx('style', { children: STUDIO_CSS }, 'css'),
    jsx('div', { ref, className: 'h64s-mount', style: { position: 'absolute', inset: 0 } }, 'mount-' + epoch)
  ]
  if (frame && frame.url) {
    children.push(jsx('div', {
      className: 'h64s-frame-layer',
      style: { position: 'absolute', left: frame.rect.left + 'px', top: frame.rect.top + 'px', width: frame.rect.width + 'px', height: frame.rect.height + 'px', zIndex: 60 },
      children: jsx(SandboxedFrame, { src: frame.url, title: frame.title || 'Hermes64 game', style: { width: '100%', height: '100%', border: '0', display: 'block' } })
    }, 'frame'))
  }
  return jsx('div', { className: 'h64s-host', style: { position: 'relative', width: '100%', height: '100%', minHeight: '360px', overflow: 'hidden' }, children })
}

function StudioRack(props) {
  const ctx = props.ctx
  const ref = useRef(null)
  useEffect(() => {
    if (!ref.current) return undefined
    const el = document.createElement('div')
    el.style.cssText = 'position:absolute;inset:0'
    ref.current.appendChild(el)
    let gone = false
    let api = null
    const follow = id => { if (api) api.select(id) }
    selection.listeners.add(follow)
    bootRack(el, { host: studioHost(ctx, { setFrame() {} }) })
      .then(a => { if (gone) { a.dispose(); return } api = a; if (selection.id) a.select(selection.id) })
      .catch(err => host.notifyError(err, 'The Studio rack could not load'))
    return () => { gone = true; selection.listeners.delete(follow); if (api) api.dispose(); el.remove() }
  }, [])
  return jsxs('div', { className: 'h64s-rack-host', style: { position: 'relative', width: '100%', height: '100%' }, children: [
    jsx('style', { children: STUDIO_CSS }),
    jsx('div', { ref, style: { position: 'absolute', inset: 0 } })
  ] })
}

export default {
  id: 'hermes64',
  name: 'Hermes64 Studio',
  register(ctx) {
    ctx.registerMany([
      {
        id: 'studio',
        area: ROUTES_AREA,
        title: 'Studio',
        data: { path: STUDIO_PATH },
        render: () => jsx(StudioPage, { ctx })
      },
      {
        id: 'studio-nav',
        area: SIDEBAR_NAV_AREA,
        title: 'Studio',
        data: { path: STUDIO_PATH, label: 'Studio', codicon: 'game' }
      },
      {
        // Third tab in the sessions zone, after SESSIONS | BOTS (one-time adoption;
        // the user may drag it elsewhere, and closing it only hides it).
        id: 'studio-tab',
        area: PANES_AREA,
        title: 'Studio',
        data: { placement: 'left', width: '260px', collapsible: true, hideOnly: true, tabTitleText: () => 'Studio', dock: { pane: 'sessions', pos: 'center' } },
        render: () => jsx(StudioRack, { ctx })
      }
    ])
    ctx.onDispose(() => { ctx.rest('/studio/stop', { method: 'POST', body: {} }).catch(() => null) })
  }
}
