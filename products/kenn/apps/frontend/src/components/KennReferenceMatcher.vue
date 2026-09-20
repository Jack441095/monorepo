<template>
  <div class="ref-matcher">
    <!-- Header & File Ingestion Dropzones -->
    <div class="ref-matcher__dropzones">
      <div
        class="ref-matcher__dropzone"
        :class="{ 'is-active': mixFile, 'is-dragging': isDraggingMix }"
        @dragover.prevent="isDraggingMix = true"
        @dragleave.prevent="isDraggingMix = false"
        @drop.prevent="onDropMix"
      >
        <div class="ref-matcher__dropzone-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M9 18V5l12-2v13" />
            <circle cx="6" cy="18" r="3" />
            <circle cx="18" cy="16" r="3" />
          </svg>
        </div>
        <div class="ref-matcher__dropzone-meta">
          <strong>Your Mixdown Track</strong>
          <span v-if="mixFile">{{ mixFile.name }} ({{ formatFileSize(mixFile.size) }})</span>
          <span v-else class="ref-matcher__hint">Drag & drop WAV / AIFF / FLAC mixdown</span>
        </div>
        <label class="ref-matcher__browse-btn">
          <input type="file" accept="audio/*,.wav,.aif,.aiff,.flac" @change="onPickMix" />
          {{ mixFile ? 'Replace' : 'Browse' }}
        </label>
      </div>

      <div
        class="ref-matcher__dropzone"
        :class="{ 'is-active': refFile, 'is-dragging': isDraggingRef }"
        @dragover.prevent="isDraggingRef = true"
        @dragleave.prevent="isDraggingRef = false"
        @drop.prevent="onDropRef"
      >
        <div class="ref-matcher__dropzone-icon ref-matcher__dropzone-icon--gold">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </div>
        <div class="ref-matcher__dropzone-meta">
          <strong>Commercial Reference Track</strong>
          <span v-if="refFile">{{ refFile.name }} ({{ formatFileSize(refFile.size) }})</span>
          <span v-else class="ref-matcher__hint">Drag & drop target reference WAV / AIFF</span>
        </div>
        <label class="ref-matcher__browse-btn">
          <input type="file" accept="audio/*,.wav,.aif,.aiff,.flac" @change="onPickRef" />
          {{ refFile ? 'Replace' : 'Browse' }}
        </label>
      </div>
    </div>

    <!-- Match Action Button -->
    <div class="ref-matcher__action-bar">
      <button
        type="button"
        class="ref-matcher__match-btn"
        :disabled="!mixFile || !refFile || isAnalyzing"
        @click="runReferenceMatch"
      >
        <span v-if="isAnalyzing" class="ref-matcher__spinner" />
        <span>{{ isAnalyzing ? 'Analyzing 7-Band Spectral & Dynamic Deltas…' : 'Match Mixdown to Reference' }}</span>
      </button>
      <span v-if="errorMessage" class="ref-matcher__error">{{ errorMessage }}</span>
    </div>

    <!-- Results Area -->
    <div v-if="matchResult && matchResult.matching" class="ref-matcher__results">
      <!-- Top Overview Bar: Preset Download & Stereo/Dynamics Gauges -->
      <div class="ref-matcher__header-card">
        <div class="ref-matcher__header-left">
          <div class="ref-matcher__badge">Live 12 Matching Profile</div>
          <h3>Ableton Live 12 EQ Eight Match Ready</h3>
          <p>
            Corrective spectral delta curves and dynamic compression envelopes calculated against
            reference track.
          </p>
        </div>
        <div class="ref-matcher__header-right">
          <a
            v-if="matchResult.preset_download_url"
            :href="getApiBase() + matchResult.preset_download_url"
            class="ref-matcher__download-btn"
            download
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>Download EQ Eight Preset (.adv)</span>
          </a>
        </div>
      </div>

      <!-- Metrics Row: Dynamics & Stereo Correlation -->
      <div class="ref-matcher__metrics-row">
        <div class="ref-matcher__metric-tile">
          <span class="ref-matcher__metric-label">Crest Factor Delta</span>
          <strong
            :class="
              (matchResult.matching.dynamics?.crest_delta_db ?? 0) < 0
                ? 'is-warn'
                : 'is-ok'
            "
          >
            {{ formatDelta(matchResult.matching.dynamics?.crest_delta_db) }} dB
          </strong>
          <small>
            Mix: {{ formatDb(matchResult.matching.dynamics?.mix_crest_factor_db) }} dB · Ref:
            {{ formatDb(matchResult.matching.dynamics?.ref_crest_factor_db) }} dB
          </small>
        </div>

        <div class="ref-matcher__metric-tile">
          <span class="ref-matcher__metric-label">RMS Loudness Delta</span>
          <strong>{{ formatDelta(matchResult.matching.dynamics?.rms_delta_db) }} dB</strong>
          <small>
            Mix: {{ formatDb(matchResult.matching.dynamics?.mix_rms_db) }} dBFS · Ref:
            {{ formatDb(matchResult.matching.dynamics?.ref_rms_db) }} dBFS
          </small>
        </div>

        <div class="ref-matcher__metric-tile">
          <span class="ref-matcher__metric-label">Stereo Correlation</span>
          <strong>{{ formatValue(matchResult.matching.stereo?.mix_correlation, 2) }}</strong>
          <small>Target Ref: {{ formatValue(matchResult.matching.stereo?.ref_correlation, 2) }}</small>
        </div>

        <div class="ref-matcher__metric-tile">
          <span class="ref-matcher__metric-label">Sub-120Hz Mono Audit</span>
          <strong :class="matchResult.matching.stereo?.mono_compatible ? 'is-ok' : 'is-bad'">
            {{ matchResult.matching.stereo?.mono_compatible ? 'Safe (Mono Clean)' : 'Phase Risk' }}
          </strong>
          <small>{{ matchResult.matching.stereo?.stereo_balance_advice || 'Low-end aligned' }}</small>
        </div>
      </div>

      <!-- 7-Band Interactive Delta Spectrum Graph -->
      <div class="ref-matcher__spectrum-card">
        <div class="ref-matcher__spectrum-head">
          <h4>7-Band Spectral Delta Matcher</h4>
          <div class="ref-matcher__legend">
            <span class="legend-item legend-item--boost"><i /> Boost Needed in Mix</span>
            <span class="legend-item legend-item--cut"><i /> Cut Needed in Mix</span>
            <span class="legend-item legend-item--ok"><i /> Balanced (±0.5 dB)</span>
          </div>
        </div>

        <div class="ref-matcher__bands-grid">
          <div
            v-for="band in bandList"
            :key="band.key"
            class="ref-matcher__band-col"
            :class="getBandStateClass(band.delta)"
          >
            <div class="ref-matcher__band-header">
              <span class="band-name">{{ band.name }}</span>
              <span class="band-hz">{{ band.hz }}</span>
            </div>

            <!-- Visual Bi-directional Meter -->
            <div class="ref-matcher__meter-track">
              <div class="ref-matcher__center-line" />
              <!-- Bar rendering: height or width depending on delta -->
              <div
                class="ref-matcher__meter-bar"
                :style="getMeterBarStyle(band.delta)"
              />
            </div>

            <div class="ref-matcher__band-footer">
              <strong class="band-delta">{{ formatDelta(band.delta) }} dB</strong>
              <span class="band-action">{{ getBandActionLabel(band.delta) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Actionable Ableton Device Recommendations -->
      <div
        v-if="matchResult.matching.device_recommendations?.length"
        class="ref-matcher__devices-card"
      >
        <h4>Recommended Ableton Live 12 Device Actions</h4>
        <div class="ref-matcher__device-grid">
          <div
            v-for="(dev, idx) in matchResult.matching.device_recommendations"
            :key="idx"
            class="ref-matcher__device-item"
          >
            <div class="ref-matcher__device-header">
              <span class="device-pill">{{ dev.device }}</span>
              <span class="device-role">{{ dev.role }}</span>
            </div>
            <p class="device-summary">{{ dev.summary }}</p>
            <ul class="device-actions">
              <li v-for="(act, aIdx) in dev.actions" :key="aIdx">{{ act }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getApiBase } from '../api/client'
import { submitReferenceMatch } from '../api/mixReview'
import type { ReferenceMatchResult } from '../utils/mixReviewTypes'

const props = defineProps<{
  initialMixFile?: File | null
  initialRefFile?: File | null
}>()

const mixFile = ref<File | null>(props.initialMixFile ?? null)
const refFile = ref<File | null>(props.initialRefFile ?? null)
const isDraggingMix = ref(false)
const isDraggingRef = ref(false)
const isAnalyzing = ref(false)
const errorMessage = ref('')
const matchResult = ref<ReferenceMatchResult | null>(null)

const BAND_SPECS: Array<{ key: string; name: string; hz: string }> = [
  { key: 'sub', name: 'Sub', hz: '20–60 Hz' },
  { key: 'bass', name: 'Bass', hz: '60–250 Hz' },
  { key: 'low_mids', name: 'Low Mids', hz: '250–500 Hz' },
  { key: 'mids', name: 'Mids', hz: '500–2 kHz' },
  { key: 'presence', name: 'Presence', hz: '2–4 kHz' },
  { key: 'sibilance', name: 'Sibilance', hz: '4–8 kHz' },
  { key: 'air', name: 'Air', hz: '8–20 kHz' },
]

const bandList = computed(() => {
  const bands = matchResult.value?.matching?.spectral_bands || {}
  return BAND_SPECS.map((spec) => {
    const data = bands[spec.key]
    const delta = data?.delta_db ?? 0
    return {
      ...spec,
      mixDb: data?.mix_db ?? 0,
      refDb: data?.ref_db ?? 0,
      delta,
    }
  })
})

function onPickMix(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files[0]) {
    mixFile.value = target.files[0]
  }
}

function onPickRef(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files[0]) {
    refFile.value = target.files[0]
  }
}

function onDropMix(e: DragEvent) {
  isDraggingMix.value = false
  if (e.dataTransfer?.files && e.dataTransfer.files[0]) {
    mixFile.value = e.dataTransfer.files[0]
  }
}

function onDropRef(e: DragEvent) {
  isDraggingRef.value = false
  if (e.dataTransfer?.files && e.dataTransfer.files[0]) {
    refFile.value = e.dataTransfer.files[0]
  }
}

async function runReferenceMatch() {
  if (!mixFile.value || !refFile.value) return
  isAnalyzing.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    form.append('mix', mixFile.value)
    form.append('reference', refFile.value)
    const result = await submitReferenceMatch(form)
    matchResult.value = result
  } catch (err: unknown) {
    errorMessage.value = err instanceof Error ? err.message : 'Reference matching failed'
  } finally {
    isAnalyzing.value = false
  }
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '0 B'
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB`
}

function formatDelta(val?: number): string {
  if (val === undefined || val === null || isNaN(val)) return '0.0'
  const prefix = val > 0 ? '+' : ''
  return `${prefix}${val.toFixed(1)}`
}

function formatDb(val?: number): string {
  if (val === undefined || val === null || isNaN(val)) return '--'
  return val.toFixed(1)
}

function formatValue(val?: number, digits = 1): string {
  if (val === undefined || val === null || isNaN(val)) return '--'
  return val.toFixed(digits)
}

function getBandStateClass(delta: number): string {
  if (Math.abs(delta) <= 0.5) return 'is-balanced'
  return delta < 0 ? 'is-boost' : 'is-cut'
}

function getBandActionLabel(delta: number): string {
  if (Math.abs(delta) <= 0.5) return 'Balanced'
  // If delta is negative, mix < ref -> Boost needed
  if (delta < 0) return `+${Math.abs(delta).toFixed(1)} dB Boost`
  // If delta is positive, mix > ref -> Cut needed
  return `-${delta.toFixed(1)} dB Cut`
}

function getMeterBarStyle(delta: number) {
  // Clamp delta to +-12 dB for visual rendering
  const clamped = Math.max(-12, Math.min(12, delta))
  const percent = (Math.abs(clamped) / 12) * 45 // max 45% of height from center
  if (delta < 0) {
    // Boost needed (positive adjustment to mix): extends upwards from center
    return {
      bottom: '50%',
      height: `${percent}%`,
      background: '#22c55e',
    }
  } else if (delta > 0) {
    // Cut needed (negative adjustment to mix): extends downwards from center
    return {
      top: '50%',
      height: `${percent}%`,
      background: '#f59e0b',
    }
  }
  return {
    top: '49%',
    height: '2%',
    background: '#64748b',
  }
}
</script>

<style scoped lang="less">
.ref-matcher {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: #e2e8f0;

  &__dropzones {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }
  }

  &__dropzone {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px dashed rgba(148, 163, 184, 0.25);
    border-radius: 8px;
    transition: all 0.2s ease;

    &.is-dragging {
      border-color: #38bdf8;
      background: rgba(56, 189, 248, 0.08);
    }

    &.is-active {
      border-style: solid;
      border-color: rgba(56, 189, 248, 0.4);
      background: rgba(15, 23, 42, 0.85);
    }
  }

  &__dropzone-icon {
    width: 36px;
    height: 36px;
    border-radius: 6px;
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;

    svg {
      width: 20px;
      height: 20px;
    }

    &--gold {
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
    }
  }

  &__dropzone-meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong {
      font-size: 13px;
      color: #f1f5f9;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    span {
      font-size: 11px;
      color: #94a3b8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }

  &__browse-btn {
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 4px;
    background: rgba(148, 163, 184, 0.15);
    color: #cbd5e1;
    cursor: pointer;
    transition: background 0.15s ease;

    &:hover {
      background: rgba(148, 163, 184, 0.25);
    }

    input {
      display: none;
    }
  }

  &__action-bar {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__match-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
    border-radius: 6px;
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    color: #ffffff;
    border: none;
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(2, 132, 199, 0.3);
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background: linear-gradient(135deg, #0369a1 0%, #075985 100%);
      box-shadow: 0 4px 10px rgba(2, 132, 199, 0.4);
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }

  &__spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #ffffff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  &__error {
    font-size: 12px;
    color: #f87171;
  }

  &__results {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  &__header-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: linear-gradient(90deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 8px;
    gap: 16px;

    @media (max-width: 800px) {
      flex-direction: column;
      align-items: flex-start;
    }
  }

  &__header-left {
    h3 {
      font-size: 16px;
      font-weight: 600;
      color: #f8fafc;
      margin: 4px 0 2px 0;
    }

    p {
      font-size: 12px;
      color: #94a3b8;
      margin: 0;
    }
  }

  &__badge {
    display: inline-block;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-radius: 4px;
    background: rgba(56, 189, 248, 0.15);
    color: #38bdf8;
  }

  &__download-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 18px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 6px;
    background: #22c55e;
    color: #052e16;
    text-decoration: none;
    transition: all 0.2s ease;
    box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);

    svg {
      width: 16px;
      height: 16px;
    }

    &:hover {
      background: #16a34a;
      color: #ffffff;
    }
  }

  &__metrics-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;

    @media (max-width: 800px) {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  &__metric-tile {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 6px;

    strong {
      font-size: 17px;
      font-weight: 700;
      color: #f1f5f9;

      &.is-ok {
        color: #4ade80;
      }
      &.is-warn {
        color: #fbbf24;
      }
      &.is-bad {
        color: #f87171;
      }
    }

    small {
      font-size: 10px;
      color: #94a3b8;
    }
  }

  &__metric-label {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }

  &__spectrum-card {
    padding: 16px 20px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  &__spectrum-head {
    display: flex;
    align-items: center;
    justify-content: space-between;

    h4 {
      font-size: 14px;
      font-weight: 600;
      color: #f1f5f9;
      margin: 0;
    }
  }

  &__legend {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 11px;
    color: #94a3b8;

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;

      i {
        width: 8px;
        height: 8px;
        border-radius: 2px;
      }

      &--boost i {
        background: #22c55e;
      }
      &--cut i {
        background: #f59e0b;
      }
      &--ok i {
        background: #64748b;
      }
    }
  }

  &__bands-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 8px;
    height: 220px;
  }

  &__band-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: rgba(30, 41, 59, 0.4);
    border: 1px solid rgba(148, 163, 184, 0.1);
    border-radius: 6px;
    padding: 8px 4px;
    position: relative;

    &.is-boost {
      border-color: rgba(34, 197, 94, 0.25);
    }
    &.is-cut {
      border-color: rgba(245, 158, 11, 0.25);
    }
  }

  &__band-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;

    .band-name {
      font-size: 11px;
      font-weight: 600;
      color: #f1f5f9;
    }

    .band-hz {
      font-size: 9px;
      color: #64748b;
    }
  }

  &__meter-track {
    flex: 1;
    width: 24px;
    margin: 8px 0;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 3px;
    position: relative;
    overflow: hidden;
  }

  &__center-line {
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(148, 163, 184, 0.4);
    z-index: 1;
  }

  &__meter-bar {
    position: absolute;
    left: 2px;
    right: 2px;
    border-radius: 2px;
    transition: all 0.3s ease;
  }

  &__band-footer {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;

    .band-delta {
      font-size: 12px;
      font-weight: 700;
      color: #f1f5f9;
    }

    .band-action {
      font-size: 9px;
      color: #94a3b8;
      text-align: center;
    }
  }

  &__devices-card {
    padding: 16px 20px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 12px;

    h4 {
      font-size: 14px;
      font-weight: 600;
      color: #f1f5f9;
      margin: 0;
    }
  }

  &__device-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }
  }

  &__device-item {
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 6px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  &__device-header {
    display: flex;
    align-items: center;
    gap: 8px;

    .device-pill {
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      background: #38bdf8;
      color: #082f49;
    }

    .device-role {
      font-size: 11px;
      color: #94a3b8;
    }
  }

  .device-summary {
    font-size: 12px;
    color: #cbd5e1;
    margin: 0;
  }

  .device-actions {
    margin: 4px 0 0 0;
    padding-left: 16px;
    font-size: 11px;
    color: #94a3b8;

    li {
      margin-bottom: 2px;
    }
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
