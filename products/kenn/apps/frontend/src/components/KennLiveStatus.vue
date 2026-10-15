<template>
  <section class="live-status" aria-label="Ableton Live status">
    <div class="live-status__connection">
      <span class="live-status__dot" :class="{ 'live-status__dot--online': project.connected }" />
      <strong>{{ project.connected ? 'Live connected' : 'Live offline' }}</strong>
      <button
        type="button"
        class="live-status__toggle-btn"
        :class="{ 'is-active': realtimeAnalysisEnabled }"
        :title="realtimeAnalysisEnabled ? 'Pause Live session polling' : 'Resume Live session polling'"
        @click="toggleRealtimeAnalysis()"
      >
        {{ realtimeAnalysisEnabled ? 'Live sync ON' : 'Live sync paused' }}
      </button>
      <button type="button" class="live-status__refresh-btn" :disabled="refreshing" title="Refresh Live status" @click="refresh">
        {{ refreshing ? 'Checking…' : 'Refresh' }}
      </button>
    </div>
    <div class="live-status__facts">
      <span><small>Session</small>{{ project.name }}</span>
      <span><small>Tracks</small>{{ project.trackCount }}</span>
      <span><small>Mode</small>{{ realtimeAnalysisEnabled ? 'Live Sync' : 'Paused' }}</span>
      <span><small>Action</small>{{ lastActionLabel }}</span>
    </div>
    <div v-if="pluginInsertId" class="live-status__audio" role="region" aria-label="Insert audio analysis">
      <label>
        Audio source
        <select :value="pluginInsertId" :disabled="pluginAudioBusy" @change="selectSource">
          <option v-if="!selectedPluginSource" :value="pluginInsertId">Launch insert · {{ pluginInsertId.slice(-8) }}</option>
          <option v-for="source in pluginSources" :key="source.insert_id" :value="source.insert_id">
            {{ source.host_track_name || 'Unnamed insert' }} · {{ source.insert_id.slice(-8) }}
          </option>
        </select>
      </label>
      <span role="status">{{ pluginAudioStatus }}<template v-if="selectedPluginSource"> · {{ selectedPluginSource.audio_age_seconds.toFixed(1) }} s old</template></span>
      <button type="button" class="live-status__refresh-btn" :disabled="pluginAudioBusy || !!pluginSourceError"
        @click="setPluginAudioEnabled(!pluginAudioRequestedEnabled)">
        {{ pluginAudioBusy ? 'Requesting…' : pluginAudioRequestedEnabled ? 'Pause audio analysis' : 'Start audio analysis' }}
      </button>
      <small v-if="pluginSourceError" role="alert">{{ pluginSourceError }}</small>
      <small v-else>Measurements from this insert; raw audio stays local. Keep its editor open to receive Start/Pause requests.</small>
      <div class="live-status__grade" role="region" aria-label="Selected insert grade">
        <strong>Selected insert · {{ selectedPluginSource?.host_track_name || 'Unnamed insert' }} · 100 ms window</strong>
        <template v-if="selectedPluginGrade">
          <p v-if="selectedPluginGrade.status === 'graded'" class="live-status__grade-score">
            {{ selectedPluginGrade.grade.points }} of {{ selectedPluginGrade.grade.points_available }} points available · {{ selectedPluginGrade.grade.full_marks }} possible
          </p>
          <p v-else><strong>Not graded.</strong> {{ selectedPluginGrade.reason }}</p>
          <p>{{ selectedPluginGrade.grade.meaning }}</p>
          <p v-if="selectedPluginGrade.stereo">
            Stereo correlation {{ selectedPluginGrade.stereo.correlation.toFixed(3) }} · {{ selectedPluginGrade.stereo.points }} of 6 stereo points.
            {{ selectedPluginGrade.stereo.points_lost }} points deducted · {{ selectedPluginGrade.stereo.threshold_band }}.
            Source: {{ selectedPluginGrade.stereo.source }} · Tier: {{ selectedPluginGrade.stereo.tier }}.
          </p>
          <ul>
            <li v-for="part in selectedPluginGrade.grade.parts" :key="part.part">
              {{ partNames[part.part] }}: {{ part.points_available ? `${part.points} of ${part.points_available} points available` : 'Not graded' }}.
              {{ part.full_marks - part.points_available }} of {{ part.full_marks }} possible points left out. {{ part.note }}
            </li>
            <li v-for="part in selectedPluginGrade.grade.ungraded" :key="part.part">
              {{ partNames[part.part as keyof typeof partNames] || part.part }}: Not graded. {{ part.reason }}
            </li>
          </ul>
          <ul>
            <li v-for="dimension in selectedPluginGrade.unscored_dimensions" :key="dimension.dimension">
              {{ dimensionNames[dimension.dimension] || dimension.dimension }} — Not graded: {{ dimension.reason }}
            </li>
          </ul>
        </template>
        <p v-else><strong>Not graded.</strong> A grade needs current stereo evidence from the selected insert.</p>
      </div>
    </div>
    <small v-else class="live-status__audio-hint">Open KENN from a plug-in insert to analyse its live audio.</small>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useKenn } from '../composables/useKenn'

const { project, lastActionAt, refreshSessionCard, realtimeAnalysisEnabled, toggleRealtimeAnalysis,
  pluginInsertId, pluginSources, selectedPluginSource, pluginAudioStatus, pluginAudioRequestedEnabled,
  pluginSourceError, pluginAudioBusy, selectedPluginGrade, refreshPluginSourceAge,
  refreshPluginSources, selectPluginInsert, setPluginAudioEnabled } = useKenn()
const partNames = { technical_health: 'Technical health', declared_target: 'Declared target', reference_match: 'Reference match' }
const dimensionNames: Record<string, string> = { dynamic_health: 'Dynamic health', low_end_control: 'Low-end control',
  spectral_balance: 'Spectral balance', stem_separation: 'Stem separation', stereo_imaging: 'Stereo imaging' }
const refreshing = ref(false)
let sourceRefreshing = false

async function refreshSources() {
  if (sourceRefreshing) return // Slow companion responses cannot accumulate overlapping polls.
  sourceRefreshing = true
  try { await refreshPluginSources() } finally { sourceRefreshing = false }
}

function selectSource(event: Event) {
  selectPluginInsert((event.target as HTMLSelectElement).value)
  void refreshSources()
}

const lastActionLabel = computed(() => {
  if (!lastActionAt.value) return 'None yet'
  return lastActionAt.value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await Promise.all([refreshSessionCard(), refreshSources()])
  } finally {
    refreshing.value = false
  }
}

let refreshTimer: number | undefined
let sourceTimer: number | undefined
onMounted(() => {
  document.addEventListener('visibilitychange', refreshPluginSourceAge)
  void refreshSources()
  if (pluginInsertId.value) sourceTimer = window.setInterval(() => {
    if (!document.hidden) void refreshSources()
  }, 1000) // One status read per second; native feature publishing stays at 2 Hz.
  refreshTimer = window.setInterval(() => {
    if (realtimeAnalysisEnabled.value) {
      void refresh()
    }
  }, 10_000)
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', refreshPluginSourceAge)
  if (refreshTimer != null) window.clearInterval(refreshTimer)
  if (sourceTimer != null) window.clearInterval(sourceTimer)
})
</script>

<style scoped lang="less">
.live-status {
  flex-shrink: 0;
  padding: 0.09rem 0.14rem 0.1rem;
  border-bottom: 1px solid var(--floating-border);
  background: color-mix(in srgb, var(--floating-bg) 88%, #0d1117);

  &__audio {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.06rem;
    margin-top: 0.08rem;
    font-size: 0.11rem;

    label { display: flex; align-items: center; gap: 0.06rem; }
    select { max-width: 1.9rem; background: var(--floating-bg); color: var(--text-color); font: inherit; }
    small { flex-basis: 100%; color: var(--muted-text); }
    [role='alert'] { color: #ef6461; }
  }

  &__audio-hint { display: block; margin-top: 0.08rem; font-size: 0.1rem; color: var(--muted-text); }

  &__grade {
    flex-basis: 100%;
    padding: 0.08rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    color: var(--muted-text);
    strong, &-score { color: var(--text-color); }
    p { margin: 0.04rem 0; }
    ul { margin: 0.04rem 0; padding-left: 0.16rem; }
  }

  &__connection {
    display: flex;
    align-items: center;
    gap: 0.07rem;
    font-size: 0.13rem;
  }

  &__toggle-btn {
    margin-left: auto;
    padding: 0.02rem 0.07rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.1rem;
    background: color-mix(in srgb, var(--floating-bg) 80%, #000);
    color: var(--muted-text);
    font: inherit;
    font-size: 0.11rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      border-color: var(--floating-border-active);
      color: var(--text-color);
    }

    &.is-active {
      background: color-mix(in srgb, #37d67a 15%, var(--floating-bg));
      border-color: rgba(55, 214, 122, 0.4);
      color: #37d67a;
    }
  }

  &__refresh-btn {
    padding: 0 0.04rem;
    border: 0;
    background: transparent;
    color: var(--muted-text);
    font: inherit;
    font-size: 0.11rem;
    cursor: pointer;

    &:hover {
      color: var(--text-color);
    }
  }

  &__dot {
    width: 0.08rem;
    height: 0.08rem;
    border-radius: 50%;
    background: #ef6461;
    box-shadow: 0 0 0.08rem rgba(239, 100, 97, 0.5);

    &--online {
      background: #37d67a;
      box-shadow: 0 0 0.09rem rgba(55, 214, 122, 0.62);
    }
  }

  &__facts {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) 0.5fr 0.8fr 0.8fr;
    gap: 0.08rem;
    margin-top: 0.08rem;

    span {
      min-width: 0;
      overflow: hidden;
      color: var(--text-color);
      font-size: 0.12rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    small {
      display: block;
      margin-bottom: 0.015rem;
      color: var(--muted-text);
      font-size: 0.095rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
  }
}
</style>
