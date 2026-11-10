// Stepped motion: smooth curves sampled at a deliberately low frame rate, the
// held-frame feel of late-90s console menus. Pure math, shared with the plugin.

export const EASE = {
  linear: t => t,
  outCubic: t => 1 - Math.pow(1 - t, 3),
  inCubic: t => t * t * t,
  outBack: t => {
    const c1 = 1.9
    const c3 = c1 + 1
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
  },
  inOutQuad: t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
}

// Fraction of `duration` elapsed, quantised to whole frames at `fps`.
export function stepped(elapsed, duration, fps) {
  if (duration <= 0) return 1
  const frame = 1000 / fps
  return Math.min(1, (Math.floor(Math.max(0, elapsed) / frame) * frame) / duration)
}

// A retargetable value. Changing the target mid-flight starts from where the
// value currently is, so held keys never snap or stutter backwards.
export class Tween {
  constructor(value) {
    this.from = value
    this.to = value
    this.start = 0
    this.duration = 0
    this.fps = 30
    this.ease = EASE.outCubic
  }

  set(to, now, duration, fps = 30, ease = EASE.outCubic) {
    if (to === this.to && this.duration > 0) return
    this.from = this.value(now)
    this.to = to
    this.start = now
    this.duration = duration
    this.fps = fps
    this.ease = ease
  }

  jump(to) {
    this.from = to
    this.to = to
    this.duration = 0
  }

  value(now) {
    if (this.duration <= 0) return this.to
    const t = stepped(now - this.start, this.duration, this.fps)
    return this.from + (this.to - this.from) * this.ease(t)
  }

  done(now) {
    return this.duration <= 0 || now - this.start >= this.duration
  }
}

// Idle bob of the selected cartridge: a sine sampled at a low frame rate.
export function bob(now, periodMs, amplitude, fps) {
  const frame = 1000 / fps
  const t = Math.floor(now / frame) * frame
  return Math.sin((t / periodMs) * Math.PI * 2) * amplitude
}

// Horizontal layout of the carousel around a floating scroll position.
// Neighbours of the focus slot are pushed out so the enlarged cart never overlaps.
export function slotX(index, scroll, slot, push) {
  const d = index - scroll
  const away = Math.max(-1, Math.min(1, d))
  return d * slot + away * push
}

export function slotScale(index, scroll, focusScale) {
  const d = Math.abs(index - scroll)
  return d >= 1 ? 1 : focusScale - (focusScale - 1) * d
}
