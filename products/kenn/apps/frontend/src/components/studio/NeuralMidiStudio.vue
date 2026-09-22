<template>
  <div class="midi-studio">
    <!-- Header Controls -->
    <div class="midi-studio__header">
      <div class="midi-studio__title-group">
        <h3 class="midi-studio__title">Neural MIDI Studio & AudioGen Groove Engine</h3>
        <span class="midi-studio__subtitle">Harmonic Bassline Generation & MPC-Grade Humanization</span>
      </div>

      <div class="midi-studio__controls-bar">
        <!-- Scale Selector -->
        <label class="midi-studio__select-group">
          <span>Key / Scale:</span>
          <select v-model="selectedScale" :disabled="isGenerating">
            <option value="F:minor">F Minor (DNB/Dubstep)</option>
            <option value="D:dorian">D Dorian (House/Tech)</option>
            <option value="A:minor">A Minor (Melodic/Trap)</option>
            <option value="E:phrygian">E Phrygian (Dark Cyber)</option>
            <option value="G:mixolydian">G Mixolydian (Funk/Soul)</option>
            <option value="C:major">C Major (Pop/Uplifting)</option>
          </select>
        </label>

        <!-- Style Selector -->
        <label class="midi-studio__select-group">
          <span>Style:</span>
          <select v-model="selectedStyle" :disabled="isGenerating">
            <option value="rolling_16th">Rolling 16th (Neuro/DNB)</option>
            <option value="syncopated_groove">Syncopated Groove (Funk/House)</option>
            <option value="sub_punch">Sub Punch (Trap/808)</option>
            <option value="offbeat_stab">Offbeat Stab (Techno/Psy)</option>
          </select>
        </label>

        <!-- Length -->
        <label class="midi-studio__select-group">
          <span>Bars:</span>
          <select v-model.number="selectedBars" :disabled="isGenerating">
            <option :value="1">1 Bar</option>
            <option :value="2">2 Bars</option>
            <option :value="4">4 Bars</option>
          </select>
        </label>

        <button
          type="button"
          class="midi-studio__generate-btn"
          :disabled="isGenerating"
          @click="generateBassline"
        >
          <span v-if="isGenerating" class="midi-studio__spinner"></span>
          <span v-else>⚡ Generate Bassline</span>
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="midi-studio__error" role="status">{{ errorMessage }}</p>

    <!-- Main Workspace Split: Top Piano Roll Canvas, Bottom Humanization Desk -->
    <div class="midi-studio__body">
      <!-- Piano Roll Display -->
      <div class="midi-studio__piano-pane">
        <div class="midi-studio__piano-head">
          <span>Interactive Piano Roll Preview ({{ notes.length }} notes)</span>
          <div class="midi-studio__scale-tag">
            Active Scale: <strong>{{ currentScaleLabel }}</strong>
          </div>
        </div>

        <div class="midi-studio__roll-wrapper" ref="rollContainer">
          <canvas ref="rollCanvas"></canvas>
        </div>
      </div>

      <!-- AudioGen Groove Humanizer Panel -->
      <div class="midi-studio__groove-pane">
        <div class="midi-studio__groove-head">
          <h4>AudioGen Groove Humanizer</h4>
          <div class="midi-studio__groove-templates">
            <button
              v-for="t in templates"
              :key="t.id"
              type="button"
              class="midi-studio__template-btn"
              :class="{ 'is-active': selectedTemplate === t.id }"
              @click="setTemplate(t.id)"
            >
              {{ t.label }}
            </button>
          </div>
        </div>

        <div class="midi-studio__sliders-grid">
          <!-- Swing Slider -->
          <div class="groove-slider">
            <div class="groove-slider__label">
              <span>Swing %</span>
              <strong>{{ swingPct }}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              v-model.number="swingPct"
              @input="onGrooveParamChange"
            />
          </div>

          <!-- Laidback Offset Slider -->
          <div class="groove-slider">
            <div class="groove-slider__label">
              <span>Timing Laidback</span>
              <strong>{{ laidbackMs >= 0 ? `+${laidbackMs}` : laidbackMs }} ms</strong>
            </div>
            <input
              type="range"
              min="-20"
              max="30"
              step="1"
              v-model.number="laidbackMs"
              @input="onGrooveParamChange"
            />
          </div>

          <!-- Velocity Jitter Slider -->
          <div class="groove-slider">
            <div class="groove-slider__label">
              <span>Velocity Jitter</span>
              <strong>{{ jitterPct }}%</strong>
            </div>
            <input
              type="range"
              min="0"
              max="50"
              step="1"
              v-model.number="jitterPct"
              @input="onGrooveParamChange"
            />
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="midi-studio__footer">
          <div class="midi-studio__target">
            <span>Target Track:</span>
            <select v-model="targetTrackIndex">
              <option v-for="tr in sessionTracks" :key="tr.index" :value="tr.index">
                Track {{ tr.index + 1 }}: {{ tr.name || 'MIDI' }}
              </option>
            </select>
          </div>

          <button
            type="button"
            class="midi-studio__commit-btn"
            :disabled="isCommitting || notes.length === 0 || !liveInsertionAvailable"
            title="Live clip insertion is a preview-only roadmap feature"
            @click="commitToLiveClip"
          >
            <span v-if="isCommitting" class="midi-studio__spinner"></span>
            <span v-else-if="committedSuccess" class="midi-studio__success">
              ✓ Injected into Live 12 Clip!
            </span>
            <span v-else>
              Preview Only — Live Insert Not Connected
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  generateMidiBassline,
  applyMidiGroove,
  fetchKennSessionCard,
  type MidiNote,
} from '../../api/kenn'

const isGenerating = ref(false)
const isCommitting = ref(false)
const committedSuccess = ref(false)
const errorMessage = ref('')
const liveInsertionAvailable = false

const selectedScale = ref('F:minor')
const selectedStyle = ref('rolling_16th')
const selectedBars = ref(2)

const selectedTemplate = ref<'lofi_swing' | 'hiphop_boombap' | 'edm_shuffle'>('lofi_swing')
const swingPct = ref(35)
const laidbackMs = ref(6)
const jitterPct = ref(15)
const targetTrackIndex = ref(1)

const notes = ref<MidiNote[]>([])

const rollContainer = ref<HTMLDivElement | null>(null)
const rollCanvas = ref<HTMLCanvasElement | null>(null)
let resizeObserver: ResizeObserver | null = null

const sessionTracks = ref<Array<{ index: number; name: string }>>([])

const templates = [
  { id: 'lofi_swing' as const, label: 'Lo-Fi MPC Swing' },
  { id: 'hiphop_boombap' as const, label: 'Boom-Bap Laidback' },
  { id: 'edm_shuffle' as const, label: 'EDM 16th Shuffle' },
]

const currentScaleLabel = computed(() => {
  return selectedScale.value.replace(':', ' ').toUpperCase()
})

function setTemplate(t: 'lofi_swing' | 'hiphop_boombap' | 'edm_shuffle') {
  selectedTemplate.value = t
  if (t === 'lofi_swing') {
    swingPct.value = 45
    laidbackMs.value = 10
    jitterPct.value = 20
  } else if (t === 'hiphop_boombap') {
    swingPct.value = 55
    laidbackMs.value = 18
    jitterPct.value = 25
  } else if (t === 'edm_shuffle') {
    swingPct.value = 25
    laidbackMs.value = 2
    jitterPct.value = 8
  }
  void onGrooveParamChange()
}

async function generateBassline() {
  isGenerating.value = true
  errorMessage.value = ''
  try {
    const res = await generateMidiBassline({
      scale: selectedScale.value,
      style: selectedStyle.value,
      bars: selectedBars.value,
    })
    if (res.notes && res.notes.length) {
      notes.value = res.notes
      await onGrooveParamChange()
    }
  } catch {
    errorMessage.value = 'Bassline generation is unavailable. Check the KENN server and try again.'
  } finally {
    isGenerating.value = false
    drawPianoRoll()
  }
}

async function onGrooveParamChange() {
  if (!notes.value.length) return
  try {
    const res = await applyMidiGroove({
      notes: notes.value,
      template: selectedTemplate.value,
      swingPct: swingPct.value,
      laidbackMs: laidbackMs.value,
      jitterPct: jitterPct.value,
    })
    if (res.notes && res.notes.length) {
      notes.value = res.notes
      drawPianoRoll()
    }
  } catch {
    errorMessage.value = 'The groove preview could not be recalculated. Your previous notes are unchanged.'
  }
}

async function commitToLiveClip() {
  committedSuccess.value = false
  errorMessage.value = 'Live clip insertion is not qualified yet. This panel is preview-only, so nothing was changed in Ableton.'
}

function drawPianoRoll() {
  const canvas = rollCanvas.value
  if (!canvas || !rollContainer.value) return
  const w = rollContainer.value.clientWidth || 600
  const h = rollContainer.value.clientHeight || 220
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  canvas.width = Math.floor(w * dpr)
  canvas.height = Math.floor(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  // Piano Roll Pitch Range (C1=36 to C4=72)
  const minPitch = 33 // A0
  const maxPitch = 57 // A2
  const pitchCount = maxPitch - minPitch + 1
  const laneHeight = h / pitchCount

  // Total Beats
  const totalBeats = selectedBars.value * 4
  const beatWidth = (w - 40) / totalBeats

  // Draw Pitch Rows (Black & White keys)
  for (let p = maxPitch; p >= minPitch; p--) {
    const idx = maxPitch - p
    const y = idx * laneHeight
    const isBlack = [1, 3, 6, 8, 10].includes(p % 12)

    ctx.fillStyle = isBlack ? '#141a24' : '#1c2433'
    ctx.fillRect(40, y, w - 40, laneHeight)

    // Key label on left
    ctx.fillStyle = isBlack ? '#64748b' : '#94a3b8'
    ctx.fillRect(0, y, 40, laneHeight)
    ctx.fillStyle = '#ffffff'
    ctx.font = '9px monospace'
    if (p % 12 === 0) {
      ctx.fillText(`C${Math.floor(p / 12) - 1}`, 6, y + laneHeight - 2)
    }
  }

  // Draw Beat Grid Lines
  for (let b = 0; b <= totalBeats * 4; b++) {
    const isBar = b % 16 === 0
    const isBeat = b % 4 === 0
    const x = 40 + (b / 4) * beatWidth

    ctx.strokeStyle = isBar
      ? 'rgba(255, 255, 255, 0.25)'
      : isBeat
      ? 'rgba(255, 255, 255, 0.1)'
      : 'rgba(255, 255, 255, 0.03)'
    ctx.lineWidth = isBar ? 1.5 : 1

    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, h)
    ctx.stroke()
  }

  // Draw Notes
  for (const note of notes.value) {
    if (note.pitch < minPitch || note.pitch > maxPitch) continue
    const idx = maxPitch - note.pitch
    const y = idx * laneHeight + 1
    const x = 40 + note.start_time * beatWidth
    const nw = Math.max(4, note.duration * beatWidth - 1)

    // Color based on velocity
    const velNorm = Math.min(1, Math.max(0, note.velocity / 127))
    const grad = ctx.createLinearGradient(x, 0, x + nw, 0)
    grad.addColorStop(0, `hsl(${210 + velNorm * 40}, 90%, ${45 + velNorm * 20}%)`)
    grad.addColorStop(1, `hsl(${190 + velNorm * 40}, 90%, ${55 + velNorm * 20}%)`)

    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.roundRect(x, y, nw, laneHeight - 2, 2)
    ctx.fill()

    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 0.5
    ctx.stroke()
  }
}

onMounted(async () => {
  try {
    const card = await fetchKennSessionCard()
    if (card?.tracks?.length) {
      sessionTracks.value = card.tracks.map((t, i) => ({
        index: t.index ?? i,
        name: t.name || `Track ${i + 1}`,
      }))
    }
  } catch {}

  drawPianoRoll()

  if (rollContainer.value) {
    resizeObserver = new ResizeObserver(() => drawPianoRoll())
    resizeObserver.observe(rollContainer.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

watch([selectedBars, notes], () => {
  drawPianoRoll()
})
</script>

<style scoped lang="less">
.midi-studio {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 0.16rem;
  background: #0f141c;
  color: #f1f5f9;
  padding: 0.16rem;
  border-radius: 0.12rem;
  box-sizing: border-box;

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.12rem;
    padding-bottom: 0.1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  &__error {
    margin: 0;
    padding: 0.08rem 0.12rem;
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 0.06rem;
    background: rgba(127, 29, 29, 0.18);
    color: #fecaca;
    font-size: 0.11rem;
  }

  &__title-group {
    display: flex;
    flex-direction: column;
    gap: 0.02rem;
  }

  &__title {
    margin: 0;
    font-size: 0.15rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }

  &__subtitle {
    font-size: 0.11rem;
    color: #94a3b8;
  }

  &__controls-bar {
    display: flex;
    align-items: center;
    gap: 0.1rem;
  }

  &__select-group {
    display: flex;
    align-items: center;
    gap: 0.04rem;
    font-size: 0.11rem;
    color: #94a3b8;

    select {
      background: #1e293b;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 0.04rem;
      padding: 0.04rem 0.06rem;
      font-size: 0.11rem;
      outline: none;
    }
  }

  &__generate-btn {
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 0.06rem;
    padding: 0.05rem 0.12rem;
    font-size: 0.12rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.04rem;
    transition: background 0.15s ease;

    &:hover:not(:disabled) {
      background: #1d4ed8;
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  &__spinner {
    width: 0.12rem;
    height: 0.12rem;
    border: 2px solid #ffffff;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  &__body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
  }

  &__piano-pane {
    flex: 1.2;
    min-height: 1.6rem;
    background: #141b26;
    border-radius: 0.08rem;
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 0.1rem;
    display: flex;
    flex-direction: column;
  }

  &__piano-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.11rem;
    color: #94a3b8;
    margin-bottom: 0.06rem;
  }

  &__scale-tag {
    font-size: 0.11rem;
    color: #60a5fa;

    strong {
      color: #93c5fd;
    }
  }

  &__roll-wrapper {
    flex: 1;
    min-height: 0;
    position: relative;
  }

  canvas {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border-radius: 0.04rem;
  }

  &__groove-pane {
    flex: 0.9;
    background: #141b26;
    border-radius: 0.08rem;
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 0.12rem;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  &__groove-head {
    display: flex;
    justify-content: space-between;
    align-items: center;

    h4 {
      margin: 0;
      font-size: 0.12rem;
      font-weight: 600;
      color: #f8fafc;
    }
  }

  &__groove-templates {
    display: flex;
    gap: 0.06rem;
  }

  &__template-btn {
    background: #1e293b;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.04rem;
    padding: 0.03rem 0.08rem;
    font-size: 0.11rem;
    color: #94a3b8;
    cursor: pointer;

    &:hover {
      border-color: rgba(255, 255, 255, 0.2);
    }

    &.is-active {
      background: rgba(37, 99, 235, 0.2);
      border-color: #3b82f6;
      color: #93c5fd;
      font-weight: 500;
    }
  }

  &__sliders-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.16rem;
  }

  &__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: auto;
    padding-top: 0.06rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  &__target {
    display: flex;
    align-items: center;
    gap: 0.06rem;
    font-size: 0.11rem;
    color: #94a3b8;

    select {
      background: #1e293b;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 0.04rem;
      padding: 0.03rem 0.06rem;
      font-size: 0.11rem;
      outline: none;
    }
  }

  &__commit-btn {
    background: #10b981;
    color: #ffffff;
    border: none;
    border-radius: 0.04rem;
    padding: 0.06rem 0.14rem;
    font-size: 0.12rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.04rem;

    &:hover:not(:disabled) {
      background: #059669;
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  &__success {
    color: #ffffff;
    font-weight: 600;
  }
}

.groove-slider {
  display: flex;
  flex-direction: column;
  gap: 0.04rem;

  &__label {
    display: flex;
    justify-content: space-between;
    font-size: 0.11rem;

    span {
      color: #94a3b8;
    }
    strong {
      color: #60a5fa;
    }
  }

  input[type='range'] {
    appearance: none;
    width: 100%;
    height: 0.04rem;
    border-radius: 0.02rem;
    background: #334155;
    outline: none;

    &::-webkit-slider-thumb {
      appearance: none;
      width: 0.12rem;
      height: 0.12rem;
      border-radius: 50%;
      background: #60a5fa;
      cursor: pointer;
    }
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
