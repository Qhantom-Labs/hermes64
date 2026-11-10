// Optional UI sound cues, addressed by Hermes64 audio-catalog id. Off by default
// (M toggles). Paths are relative to the repository's audio/ folder and are
// checked against audio/catalog.json by tests/test_studio_catalogue.py.

export const CUE_FILES = {
  'ui.move': 'wav/ui.move.wav',
  'ui.select': 'wav/ui.select.wav',
  'ui.back': 'wav/ui.back.wav',
  'hatch.open': 'wav/hatch.open.wav',
  'core.ui.move.02': 'stock/wav/core.ui.move.02.wav',
  'core.hatch.slide.open': 'stock/wav/core.hatch.slide.open.wav',
  'core.machine.computer.accept': 'stock/wav/core.machine.computer.accept.wav',
  'core.magic.chime': 'stock/wav/core.magic.chime.wav',
  'core.ui.confirm.01': 'stock/wav/core.ui.confirm.01.wav',
  'core.ui.error.01': 'stock/wav/core.ui.error.01.wav'
}

export class SoundBank {
  // resolve(id) -> Promise<url> lets a host serve the files (the desktop plugin
  // asks its backend for data URLs); without it files load from `base`.
  constructor(base, enabled = false, resolve = null) {
    this.base = base
    this.enabled = enabled
    this.resolve = resolve
    this.urls = {}
    this.pool = {}
    this.lastAt = {}
  }

  url(id) {
    if (!this.resolve) return this.base + CUE_FILES[id]
    if (this.urls[id] === undefined) {
      this.urls[id] = null
      Promise.resolve(this.resolve(id)).then(u => { this.urls[id] = u || false }).catch(() => { this.urls[id] = false })
    }
    return this.urls[id] || null
  }

  toggle() {
    this.enabled = !this.enabled
    return this.enabled
  }

  play(id) {
    if (!this.enabled || !CUE_FILES[id] || typeof Audio === 'undefined') return
    const now = Date.now()
    if (now - (this.lastAt[id] || 0) < 45) return
    this.lastAt[id] = now
    const list = this.pool[id] || (this.pool[id] = [])
    let a = list.find(x => x.paused || x.ended)
    const src = this.url(id)
    if (!src) return
    if (!a && list.length < 4) {
      a = new Audio(src)
      a.volume = 0.55
      list.push(a)
    }
    if (!a) return
    try {
      a.currentTime = 0
      const p = a.play()
      if (p && p.catch) p.catch(() => {})
    } catch (err) {
      // Autoplay or decode refusal: cues are optional, stay silent.
    }
  }
}
