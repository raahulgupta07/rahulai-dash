/**
 * useRunSound — short audio cues when an agent run starts and finishes.
 *
 * WebAudio-generated tones (no asset files, works offline). A header toggle 🔊
 * persists in localStorage. Call `playStart()` when a run begins and
 * `playFinish()` when it completes; both no-op when disabled or if the browser
 * blocks audio (fail-soft — never throws).
 */
import { ref } from 'vue'

const STORAGE_KEY = 'cag_run_sound_enabled'

// module-level singleton so every mount shares one state + one AudioContext
const enabled = ref(false)
let _hydrated = false
let _ctx: AudioContext | null = null

function hydrate() {
  if (_hydrated || typeof window === 'undefined') return
  _hydrated = true
  try {
    enabled.value = window.localStorage.getItem(STORAGE_KEY) === '1'
  } catch { /* ignore */ }
}

function getCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null
  try {
    if (!_ctx) {
      const AC = (window as any).AudioContext || (window as any).webkitAudioContext
      if (!AC) return null
      _ctx = new AC()
    }
    const ctx = _ctx as AudioContext
    // browsers suspend the context until a user gesture; resume best-effort
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    return ctx
  } catch {
    return null
  }
}

/** Play a sequence of [frequency Hz, startOffset s, duration s] notes. */
function playNotes(notes: Array<[number, number, number]>) {
  if (!enabled.value) return
  const ctx = getCtx()
  if (!ctx) return
  try {
    const now = ctx.currentTime
    for (const [freq, off, dur] of notes) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      // quick attack, smooth decay — gentle, not jarring
      gain.gain.setValueAtTime(0.0001, now + off)
      gain.gain.exponentialRampToValueAtTime(0.14, now + off + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + off + dur)
      osc.connect(gain).connect(ctx.destination)
      osc.start(now + off)
      osc.stop(now + off + dur + 0.02)
    }
  } catch { /* fail-soft */ }
}

export function useRunSound() {
  hydrate()

  function toggle() {
    enabled.value = !enabled.value
    try {
      window.localStorage.setItem(STORAGE_KEY, enabled.value ? '1' : '0')
    } catch { /* ignore */ }
    if (enabled.value) playStart() // preview + unlock audio on the enabling gesture
  }

  // start = single soft rising blip
  function playStart() {
    playNotes([[523.25, 0, 0.16]]) // C5
  }

  // finish = two-note "ta-da" (rising, success)
  function playFinish() {
    playNotes([
      [659.25, 0, 0.14],    // E5
      [880.0, 0.13, 0.22],  // A5
    ])
  }

  return { enabled, toggle, playStart, playFinish }
}
