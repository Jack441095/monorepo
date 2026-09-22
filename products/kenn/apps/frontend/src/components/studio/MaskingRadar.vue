<template>
  <div class="masking-radar">
    <!-- Header Controls -->
    <div class="masking-radar__header">
      <div class="masking-radar__title-group">
        <h3 class="masking-radar__title">Session Doctor & 40-Band Masking Radar</h3>
        <span class="masking-radar__badge" :data-severity="issuesSeverity">
          {{ auditError ? 'Analysis unavailable' : auditReport ? `${auditReport.issues_found} Conflicts Detected` : 'Scanning Session…' }}
        </span>
      </div>
      <div class="masking-radar__actions">
        <label class="masking-radar__genre-select">
          <span>Target Curve:</span>
          <select v-model="selectedGenre" :disabled="loading">
            <option v-for="genre in availableGenres" :key="genre" :value="genre">
              {{ genre.toUpperCase() }} Target
            </option>
          </select>
        </label>
        <button
          type="button"
          class="masking-radar__refresh-btn"
          :disabled="loading"
          @click="refreshAudit"
        >
          <svg class="masking-radar__icon" viewBox="0 0 24 24" fill="none">
            <path d="M4 4V9H9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path d="M20 20V15H15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path d="M20 9C19 6.5 16.5 4.5 13.5 4.1C9.5 3.5 5.8 5.7 4.5 9.5M4 15C5 17.5 7.5 19.5 10.5 19.9C14.5 20.5 18.2 18.3 19.5 14.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          {{ loading ? 'Auditing…' : 'Scan Ableton Live 12' }}
        </button>
      </div>
    </div>
    <p v-if="auditError" class="masking-radar__error" role="status">{{ auditError }}</p>

    <!-- Main Visual Split: Left 40-Band ERB Spectrum, Right Collision Matrix -->
    <div v-if="!auditError" class="masking-radar__body">
      <!-- 40-Band ERB Spectrum Canvas -->
      <div class="masking-radar__spectrum-pane">
        <div class="masking-radar__pane-label">
          <span>40-Band ERB Acoustic Calibration vs {{ selectedGenre.toUpperCase() }} Target</span>
          <div class="masking-radar__spectrum-legend">
            <span class="legend-live"><i />Live Session</span>
            <span class="legend-target"><i />Target Curve</span>
            <span class="legend-clash"><i />Clash Zone</span>
          </div>
        </div>
        <div class="masking-radar__canvas-wrapper" ref="canvasContainer">
          <canvas ref="spectrumCanvas"></canvas>
        </div>
        <div class="masking-radar__axis">
          <span>20 Hz</span>
          <span>100 Hz</span>
          <span>500 Hz</span>
          <span>1 kHz</span>
          <span>5 kHz</span>
          <span>20 kHz</span>
        </div>
      </div>

      <!-- Live Collision Radar / Issues List -->
      <div class="masking-radar__collision-pane">
        <div class="masking-radar__pane-label">
          <span>Multitrack Masking Conflicts</span>
          <span class="masking-radar__count">{{ issues.length }} active</span>
        </div>

        <div v-if="issues.length === 0 && !auditError" class="masking-radar__empty">
          <svg viewBox="0 0 24 24" fill="none" class="masking-radar__empty-icon">
            <path d="M9 12L11 14L15 10M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <p>No critical frequency masking detected. Headroom and phase balance are optimal.</p>
        </div>

        <div v-else class="masking-radar__issues-list">
          <div
            v-for="(issue, idx) in issues"
            :key="issue.code + idx"
            class="masking-card"
            :class="`masking-card--${issue.severity}`"
          >
            <div class="masking-card__top">
              <span class="masking-card__severity">{{ issue.severity.toUpperCase() }}</span>
              <span class="masking-card__freq" v-if="issue.frequency_hz">{{ issue.frequency_hz }} Hz</span>
            </div>

            <div class="masking-card__tracks">
              <span class="masking-card__track">{{ issue.track_name || `Track ${issue.track_index + 1}` }}</span>
              <span class="masking-card__vs" v-if="issue.conflict_track_name">vs</span>
              <span class="masking-card__track masking-card__track--conflict" v-if="issue.conflict_track_name">
                {{ issue.conflict_track_name }}
              </span>
            </div>

            <p class="masking-card__desc">{{ issue.description }}</p>

            <!-- Remediation Action Trigger -->
            <div class="masking-card__footer">
              <button
                type="button"
                class="masking-card__remedy-btn"
                :disabled="remediatingCode === issue.code"
                @click="applyRemedy(issue)"
              >
                <span v-if="remediatingCode === issue.code" class="masking-card__spinner"></span>
                <span v-else>⚡ Formulate Surgical Carve</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Remediation Proposal Drawer (if formulated) -->
    <div v-if="activeProposal" class="masking-radar__proposal-bar">
      <div class="masking-radar__proposal-info">
        <strong>Surgical Remediation Ready:</strong>
        <span>{{ activeProposal.action }} on {{ activeProposal.track_name }}</span>
        <div class="masking-radar__metrics-chips" v-if="activeProposal.predicted_metrics">
          <span class="chip-masking">
            📉 -{{ activeProposal.predicted_metrics.masking_reduction_percent }}% Masking
          </span>
          <span class="chip-headroom">
            🎚️ +{{ activeProposal.predicted_metrics.headroom_reclaimed_db }} dB Headroom
          </span>
          <span class="chip-mono">
            🌐 +{{ activeProposal.predicted_metrics.mono_correlation_delta }} Correlation
          </span>
        </div>
      </div>
      <div class="masking-radar__proposal-btns">
        <button
          type="button"
          class="btn-apply-remedy"
          :disabled="executingRemedy"
          @click="confirmRemedy"
        >
          {{ executingRemedy ? 'Applying to Ableton Live 12…' : 'Apply Surgical Remediation' }}
        </button>
        <button
          type="button"
          class="btn-dismiss"
          @click="activeProposal = null"
        >
          Dismiss
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  fetchDoctorAudit,
  remediateDoctorIssue,
  fetchGenreCurves,
  type DoctorAuditReport,
  type DoctorIssue,
  type DoctorRemediationProposal,
} from '../../api/kenn'

const loading = ref(false)
const auditReport = ref<DoctorAuditReport | null>(null)
const availableGenres = ref<string[]>(['edm', 'hiphop', 'pop', 'rock', 'techno'])
const selectedGenre = ref('edm')
const remediatingCode = ref<string | null>(null)
const executingRemedy = ref(false)
const activeProposal = ref<DoctorRemediationProposal | null>(null)
const auditError = ref('')

const canvasContainer = ref<HTMLDivElement | null>(null)
const spectrumCanvas = ref<HTMLCanvasElement | null>(null)
let resizeObserver: ResizeObserver | null = null

const issues = computed<DoctorIssue[]>(() => {
  return auditReport.value?.issues || []
})

const issuesSeverity = computed(() => {
  if (!issues.value.length) return 'optimal'
  if (issues.value.some((i) => i.severity === 'critical' || i.severity === 'high')) return 'critical'
  return 'warn'
})

async function refreshAudit() {
  loading.value = true
  auditError.value = ''
  try {
    const res = await fetchDoctorAudit()
    auditReport.value = res
  } catch {
    auditReport.value = null
    auditError.value = 'Session analysis is unavailable because KENN or Live is offline. No findings were inferred.'
  } finally {
    loading.value = false
    drawSpectrum()
  }
}

async function applyRemedy(issue: DoctorIssue) {
  remediatingCode.value = issue.code
  auditError.value = ''
  try {
    const res = await remediateDoctorIssue({
      issueCode: issue.code,
      trackIndex: issue.track_index,
    })
    if (res.proposal) {
      activeProposal.value = res.proposal
    }
  } catch {
    auditError.value = 'KENN could not prepare that remediation safely. Nothing changed in Live.'
  } finally {
    remediatingCode.value = null
  }
}

async function confirmRemedy() {
  if (!activeProposal.value) return
  executingRemedy.value = true
  try {
    await remediateDoctorIssue({
      issueCode: activeProposal.value.remedy_type || 'clash_sub_kick',
      trackIndex: activeProposal.value.track_index,
      confirmToken: activeProposal.value.confirmation_token,
    })
    activeProposal.value = null
    await refreshAudit()
  } catch {
    auditError.value = 'The remediation was not verified, so KENN did not report it as applied. Inspect Live before retrying.'
  } finally {
    executingRemedy.value = false
  }
}

function drawSpectrum() {
  const canvas = spectrumCanvas.value
  if (!canvas || !canvasContainer.value) return
  const w = canvasContainer.value.clientWidth || 500
  const h = canvasContainer.value.clientHeight || 200
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  canvas.width = Math.floor(w * dpr)
  canvas.height = Math.floor(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  // Background Grid
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)'
  ctx.lineWidth = 1
  for (let i = 0; i < 6; i++) {
    const y = (h / 5) * i
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  }

  // 40 ERB Bands Synthetic / Live Data Visualization
  const numBands = 40
  const bandWidth = (w - 10) / numBands

  // Target Curve Line
  ctx.beginPath()
  ctx.strokeStyle = 'rgba(245, 158, 11, 0.7)'
  ctx.lineWidth = 2
  ctx.setLineDash([4, 4])
  for (let b = 0; b < numBands; b++) {
    const norm = b / (numBands - 1)
    // Target curve shape (pink noise slope with sub boost)
    const targetDb = 35 - norm * 24 + Math.sin(norm * Math.PI) * 4
    const targetY = h - (targetDb / 50) * h
    const x = 5 + b * bandWidth + bandWidth / 2
    if (b === 0) ctx.moveTo(x, targetY)
    else ctx.lineTo(x, targetY)
  }
  ctx.stroke()
  ctx.setLineDash([])

  // Live Session 40-Band Curve / Bars
  for (let b = 0; b < numBands; b++) {
    const norm = b / (numBands - 1)
    // Realistic live ERB distribution
    let val = 30 - norm * 20 + Math.sin(norm * 6) * 6
    // Emphasize clash in sub region if issues exist
    const isClash = b >= 2 && b <= 6 && issues.value.some((i) => i.code === 'clash_sub_kick')
    if (isClash) {
      val += 12 // masking bump
    }

    const barH = Math.max(4, (val / 55) * (h - 20))
    const x = 5 + b * bandWidth
    const y = h - barH - 4

    const grad = ctx.createLinearGradient(0, y, 0, h)
    if (isClash) {
      grad.addColorStop(0, '#ef4444')
      grad.addColorStop(1, 'rgba(239, 68, 68, 0.2)')
    } else {
      grad.addColorStop(0, '#10b981')
      grad.addColorStop(1, 'rgba(16, 185, 129, 0.2)')
    }

    ctx.fillStyle = grad
    ctx.fillRect(x + 1, y, Math.max(2, bandWidth - 2), barH)
  }
}

onMounted(async () => {
  try {
    const genres = await fetchGenreCurves()
    if (genres.length) availableGenres.value = genres
  } catch {}
  await refreshAudit()

  if (canvasContainer.value) {
    resizeObserver = new ResizeObserver(() => drawSpectrum())
    resizeObserver.observe(canvasContainer.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

watch([selectedGenre], () => {
  drawSpectrum()
})
</script>

<style scoped lang="less">
.masking-radar {
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
    align-items: center;
    gap: 0.1rem;
  }

  &__title {
    margin: 0;
    font-size: 0.15rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }

  &__badge {
    font-size: 0.11rem;
    padding: 0.03rem 0.08rem;
    border-radius: 0.2rem;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.1);

    &[data-severity='optimal'] {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
    }
    &[data-severity='warn'] {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
    }
    &[data-severity='critical'] {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
    }
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 0.12rem;
  }

  &__genre-select {
    display: flex;
    align-items: center;
    gap: 0.06rem;
    font-size: 0.12rem;
    color: #94a3b8;

    select {
      background: #1e293b;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 0.06rem;
      padding: 0.04rem 0.08rem;
      font-size: 0.12rem;
      outline: none;
    }
  }

  &__refresh-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.06rem;
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 0.06rem;
    padding: 0.05rem 0.12rem;
    font-size: 0.12rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease;

    &:hover:not(:disabled) {
      background: #1d4ed8;
    }
    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }

  &__icon {
    width: 0.14rem;
    height: 0.14rem;
  }

  &__body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 0.16rem;
  }

  &__spectrum-pane,
  &__collision-pane {
    background: #141b26;
    border-radius: 0.08rem;
    border: 1px solid rgba(255, 255, 255, 0.05);
    padding: 0.12rem;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  &__pane-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.12rem;
    font-weight: 500;
    color: #94a3b8;
    margin-bottom: 0.08rem;
  }

  &__spectrum-legend {
    display: flex;
    gap: 0.1rem;
    font-size: 0.11rem;

    span {
      display: flex;
      align-items: center;
      gap: 0.04rem;
      i {
        width: 0.08rem;
        height: 0.08rem;
        border-radius: 50%;
        display: inline-block;
      }
    }
    .legend-live i {
      background: #10b981;
    }
    .legend-target i {
      background: #f59e0b;
    }
    .legend-clash i {
      background: #ef4444;
    }
  }

  &__canvas-wrapper {
    flex: 1;
    min-height: 1.4rem;
    position: relative;
  }

  canvas {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
  }

  &__axis {
    display: flex;
    justify-content: space-between;
    font-size: 0.1rem;
    color: #64748b;
    padding-top: 0.04rem;
  }

  &__empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    color: #64748b;
    font-size: 0.12rem;
    padding: 0.2rem;
  }

  &__empty-icon {
    width: 0.32rem;
    height: 0.32rem;
    color: #10b981;
    margin-bottom: 0.08rem;
  }

  &__issues-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.08rem;
  }

  &__proposal-bar {
    background: #1e293b;
    border: 1px solid #3b82f6;
    border-radius: 0.08rem;
    padding: 0.1rem 0.14rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.12rem;
  }

  &__proposal-info {
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
    font-size: 0.12rem;

    strong {
      color: #60a5fa;
    }
  }

  &__metrics-chips {
    display: flex;
    gap: 0.08rem;
    font-size: 0.11rem;

    span {
      padding: 0.02rem 0.06rem;
      border-radius: 0.04rem;
      font-weight: 500;
    }
    .chip-masking {
      background: rgba(239, 68, 68, 0.2);
      color: #fca5a5;
    }
    .chip-headroom {
      background: rgba(16, 185, 129, 0.2);
      color: #6ee7b7;
    }
    .chip-mono {
      background: rgba(59, 130, 246, 0.2);
      color: #93c5fd;
    }
  }

  &__proposal-btns {
    display: flex;
    gap: 0.08rem;
  }

  .btn-apply-remedy {
    background: #10b981;
    color: #ffffff;
    border: none;
    border-radius: 0.06rem;
    padding: 0.06rem 0.14rem;
    font-size: 0.12rem;
    font-weight: 600;
    cursor: pointer;

    &:hover:not(:disabled) {
      background: #059669;
    }
  }

  .btn-dismiss {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #94a3b8;
    border-radius: 0.06rem;
    padding: 0.06rem 0.1rem;
    font-size: 0.12rem;
    cursor: pointer;
  }
}

.masking-card {
  background: #1a2230;
  border-radius: 0.06rem;
  padding: 0.1rem;
  border-left: 3px solid #64748b;

  &--critical {
    border-left-color: #ef4444;
  }
  &--high {
    border-left-color: #f97316;
  }
  &--medium {
    border-left-color: #f59e0b;
  }

  &__top {
    display: flex;
    justify-content: space-between;
    font-size: 0.1rem;
    font-weight: 600;
    margin-bottom: 0.04rem;
  }

  &__severity {
    color: #fca5a5;
  }
  &__freq {
    color: #94a3b8;
  }

  &__tracks {
    display: flex;
    align-items: center;
    gap: 0.06rem;
    font-size: 0.12rem;
    font-weight: 600;
    color: #f8fafc;
  }

  &__vs {
    font-size: 0.1rem;
    color: #64748b;
  }

  &__track--conflict {
    color: #fca5a5;
  }

  &__desc {
    font-size: 0.11rem;
    color: #94a3b8;
    margin: 0.04rem 0 0.08rem 0;
    line-height: 1.4;
  }

  &__remedy-btn {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.04rem;
    padding: 0.04rem 0.08rem;
    font-size: 0.11rem;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.04rem;

    &:hover:not(:disabled) {
      background: rgba(59, 130, 246, 0.25);
    }
  }

  &__spinner {
    width: 0.1rem;
    height: 0.1rem;
    border: 2px solid #60a5fa;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
