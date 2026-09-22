<template>
  <div class="rack-gallery">
    <!-- Header Controls & Filters -->
    <div class="rack-gallery__header">
      <div class="rack-gallery__title-group">
        <h3 class="rack-gallery__title">12 Pro Audio Effect Rack Synthesizers</h3>
        <span class="rack-gallery__subtitle">Ableton 12 Multi-Chain DSP Chains & Macro Snapshots</span>
      </div>

      <div class="rack-gallery__filters">
        <button
          v-for="cat in categories"
          :key="cat.id"
          type="button"
          class="rack-gallery__filter-btn"
          :class="{ 'is-active': activeFilter === cat.id }"
          @click="activeFilter = cat.id"
        >
          {{ cat.label }}
        </button>
      </div>
    </div>

    <!-- Gallery Grid -->
    <div v-if="loading" class="rack-gallery__loading">
      <div class="rack-gallery__spinner"></div>
      <p>Loading Pro Audio Effect Racks…</p>
    </div>

    <div v-else-if="errorMessage" class="rack-gallery__error" role="status">
      {{ errorMessage }}
    </div>

    <div v-else class="rack-gallery__grid">
      <div
        v-for="rack in filteredRacks"
        :key="rack.key"
        class="rack-card"
        :class="{ 'is-applying': applyingKey === rack.key }"
      >
        <!-- Card Header -->
        <div class="rack-card__header">
          <div class="rack-card__title-row">
            <h4 class="rack-card__name">{{ rack.name }}</h4>
            <span class="rack-card__role-badge">{{ rack.target_role.toUpperCase() }}</span>
          </div>
          <p class="rack-card__desc">{{ rack.description }}</p>
          <div class="rack-card__chains">
            <span v-for="chain in rack.chains" :key="chain" class="rack-card__chain-tag">
              {{ chain }}
            </span>
          </div>
        </div>

        <!-- Variation Snapshot Switcher -->
        <div class="rack-card__variations" v-if="rack.variations && Object.keys(rack.variations).length">
          <span class="rack-card__section-label">Snapshot Variations:</span>
          <div class="rack-card__var-buttons">
            <button
              v-for="(varData, varKey) in rack.variations"
              :key="varKey"
              type="button"
              class="rack-card__var-btn"
              :class="{ 'is-selected': getActiveSnapshot(rack.key) === varKey }"
              @click="selectSnapshot(rack, String(varKey))"
            >
              <strong>{{ varKey }}</strong>
              <span>{{ varData.name }}</span>
            </button>
          </div>
        </div>

        <!-- 8 Macro Parameter Sliders -->
        <div class="rack-card__macros">
          <span class="rack-card__section-label">8 Macro Parameter Map:</span>
          <div class="rack-card__macros-grid">
            <div
              v-for="macro in rack.macros"
              :key="macro.name"
              class="macro-dial"
            >
              <div class="macro-dial__label-row">
                <span class="macro-dial__name">{{ macro.name }}</span>
                <span class="macro-dial__val">
                  {{ getMacroValue(rack.key, macro.name, macro.default) }}{{ macro.unit }}
                </span>
              </div>
              <input
                type="range"
                class="macro-dial__slider"
                :min="macro.min"
                :max="macro.max"
                :step="(macro.max - macro.min) / 100"
                :value="getMacroValue(rack.key, macro.name, macro.default)"
                @input="setMacroValue(rack.key, macro.name, Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
        </div>

        <!-- Card Footer & Live 12 Action -->
        <div class="rack-card__footer">
          <div class="rack-card__target-select">
            <span>Target Track:</span>
            <select v-model="targetTracks[rack.key]">
              <option v-for="tr in sessionTracks" :key="tr.index" :value="tr.index">
                Track {{ tr.index + 1 }}: {{ tr.name || 'Audio' }}
              </option>
            </select>
          </div>

          <button
            type="button"
            class="rack-card__apply-btn"
            :disabled="applyingKey === rack.key"
            @click="synthesizeRack(rack)"
          >
            <span v-if="applyingKey === rack.key" class="rack-card__spinner"></span>
            <span v-else-if="appliedStatus[rack.key]" class="rack-card__applied-status">
              ✓ {{ appliedStatus[rack.key] }}
            </span>
            <span v-else>
              Synthesize to Live 12
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  fetchProRacks,
  synthesizeProRack,
  fetchKennSessionCard,
  type ProRackDefinition,
} from '../../api/kenn'

const loading = ref(true)
const racks = ref<ProRackDefinition[]>([])
const activeFilter = ref('all')
const applyingKey = ref<string | null>(null)
const appliedStatus = reactive<Record<string, string>>({})
const errorMessage = ref('')
const targetTracks = reactive<Record<string, number>>({})
const activeSnapshots = reactive<Record<string, string>>({})
const customMacroValues = reactive<Record<string, Record<string, number>>>({})

const sessionTracks = ref<Array<{ index: number; name: string }>>([])

const categories = [
  { id: 'all', label: 'All 12 Racks' },
  { id: 'bass', label: 'Bass & Low-End' },
  { id: 'drums', label: 'Drums & Punch' },
  { id: 'vocals', label: 'Vocals' },
  { id: 'mixbus', label: 'Mix Bus & Stereo' },
]

const filteredRacks = computed(() => {
  if (activeFilter.value === 'all') return racks.value
  if (activeFilter.value === 'bass') {
    return racks.value.filter((r) => r.target_role === 'bass' || r.key.includes('bass') || r.key.includes('808'))
  }
  if (activeFilter.value === 'drums') {
    return racks.value.filter((r) => r.target_role === 'drums' || r.key.includes('drum'))
  }
  if (activeFilter.value === 'vocals') {
    return racks.value.filter((r) => r.target_role === 'vocals' || r.key.includes('vocal'))
  }
  if (activeFilter.value === 'mixbus') {
    return racks.value.filter((r) => r.target_role === 'mixbus' || r.key.includes('widener') || r.key.includes('glue') || r.key.includes('tape'))
  }
  return racks.value
})

function getActiveSnapshot(rackKey: string): string {
  return activeSnapshots[rackKey] || 'A'
}

function selectSnapshot(rack: ProRackDefinition, snapshotKey: string) {
  activeSnapshots[rack.key] = snapshotKey
  if (!customMacroValues[rack.key]) customMacroValues[rack.key] = {}
  const snap = rack.variations?.[snapshotKey]
  if (snap?.macros) {
    for (const [mName, mVal] of Object.entries(snap.macros)) {
      customMacroValues[rack.key][mName] = mVal
    }
  }
}

function getMacroValue(rackKey: string, macroName: string, defaultVal: number): number {
  if (customMacroValues[rackKey]?.[macroName] !== undefined) {
    return customMacroValues[rackKey][macroName]
  }
  return defaultVal
}

function setMacroValue(rackKey: string, macroName: string, val: number) {
  if (!customMacroValues[rackKey]) customMacroValues[rackKey] = {}
  customMacroValues[rackKey][macroName] = val
}

async function synthesizeRack(rack: ProRackDefinition) {
  applyingKey.value = rack.key
  appliedStatus[rack.key] = ''
  errorMessage.value = ''
  try {
    const trackIdx = targetTracks[rack.key] ?? 0
    const snap = getActiveSnapshot(rack.key)
    const res = await synthesizeProRack({
      rackKey: rack.key,
      trackIndex: trackIdx,
      snapshotKey: snap,
    })
    if (res.ok) {
      appliedStatus[rack.key] = `Synthesized to Track ${trackIdx + 1} (${snap})`
      setTimeout(() => {
        appliedStatus[rack.key] = ''
      }, 5000)
    }
  } catch {
    errorMessage.value = 'KENN could not prepare that rack safely. Check the Live connection and try again; nothing changed.'
  } finally {
    applyingKey.value = null
  }
}

onMounted(async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const [rackList, sessionData] = await Promise.all([
      fetchProRacks(),
      fetchKennSessionCard().catch(() => null),
    ])
    if (rackList.length) {
      racks.value = rackList
      rackList.forEach((r, idx) => {
        targetTracks[r.key] = idx % 8
        activeSnapshots[r.key] = 'A'
        selectSnapshot(r, 'A')
      })
    }
    if (sessionData?.tracks && sessionData.tracks.length > 0) {
      sessionTracks.value = sessionData.tracks.map((t, i) => ({
        index: t.index ?? i,
        name: t.name || `Track ${i + 1}`,
      }))
    }
  } catch {
    racks.value = []
    sessionTracks.value = []
    errorMessage.value = 'Pro Racks are unavailable because KENN is offline. Start the server, then reopen this panel.'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped lang="less">
.rack-gallery {
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
    padding: 0.14rem;
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 0.08rem;
    background: rgba(127, 29, 29, 0.18);
    color: #fecaca;
    font-size: 0.12rem;
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

  &__filters {
    display: flex;
    gap: 0.06rem;
  }

  &__filter-btn {
    background: #1e293b;
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #94a3b8;
    padding: 0.04rem 0.1rem;
    border-radius: 0.2rem;
    font-size: 0.11rem;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
      color: #f8fafc;
      border-color: rgba(255, 255, 255, 0.2);
    }

    &.is-active {
      background: #2563eb;
      color: #ffffff;
      border-color: #2563eb;
      font-weight: 500;
    }
  }

  &__loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 0.1rem;
    color: #94a3b8;
    font-size: 0.12rem;
  }

  &__spinner {
    width: 0.2rem;
    height: 0.2rem;
    border: 2px solid #3b82f6;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  &__grid {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(3.2rem, 1fr));
    gap: 0.14rem;
    padding-right: 0.04rem;
  }
}

.rack-card {
  background: #141b26;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.08rem;
  padding: 0.12rem;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  transition: transform 0.15s ease, border-color 0.15s ease;

  &:hover {
    border-color: rgba(59, 130, 246, 0.3);
  }

  &__header {
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
  }

  &__title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  &__name {
    margin: 0;
    font-size: 0.13rem;
    font-weight: 600;
    color: #f8fafc;
  }

  &__role-badge {
    font-size: 0.1rem;
    font-weight: 600;
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    padding: 0.02rem 0.06rem;
    border-radius: 0.04rem;
  }

  &__desc {
    margin: 0;
    font-size: 0.11rem;
    color: #94a3b8;
    line-height: 1.35;
  }

  &__chains {
    display: flex;
    flex-wrap: wrap;
    gap: 0.04rem;
    margin-top: 0.02rem;
  }

  &__chain-tag {
    font-size: 0.1rem;
    background: #1e293b;
    color: #cbd5e1;
    padding: 0.02rem 0.06rem;
    border-radius: 0.04rem;
  }

  &__section-label {
    font-size: 0.1rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.04rem;
    display: block;
  }

  &__variations {
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
  }

  &__var-buttons {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.04rem;
  }

  &__var-btn {
    background: #1e293b;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.04rem;
    padding: 0.04rem 0.06rem;
    color: #94a3b8;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.01rem;
    transition: all 0.15s ease;

    strong {
      font-size: 0.1rem;
      color: #cbd5e1;
    }

    span {
      font-size: 0.09rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
    }

    &:hover {
      border-color: rgba(255, 255, 255, 0.2);
    }

    &.is-selected {
      background: rgba(37, 99, 235, 0.2);
      border-color: #3b82f6;
      color: #93c5fd;

      strong {
        color: #60a5fa;
      }
    }
  }

  &__macros {
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
  }

  &__macros-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.06rem 0.1rem;
  }

  &__footer {
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.08rem;
    padding-top: 0.08rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  &__target-select {
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
      padding: 0.03rem 0.06rem;
      font-size: 0.11rem;
      outline: none;
      max-width: 1.1rem;
    }
  }

  &__apply-btn {
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 0.04rem;
    padding: 0.05rem 0.1rem;
    font-size: 0.11rem;
    font-weight: 500;
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

  &__applied-status {
    color: #34d399;
    font-weight: 600;
  }

  &__spinner {
    width: 0.1rem;
    height: 0.1rem;
    border: 2px solid #ffffff;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

.macro-dial {
  display: flex;
  flex-direction: column;
  gap: 0.02rem;

  &__label-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.1rem;
  }

  &__name {
    color: #cbd5e1;
  }

  &__val {
    color: #60a5fa;
    font-weight: 500;
  }

  &__slider {
    appearance: none;
    width: 100%;
    height: 0.04rem;
    border-radius: 0.02rem;
    background: #334155;
    outline: none;

    &::-webkit-slider-thumb {
      appearance: none;
      width: 0.1rem;
      height: 0.1rem;
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
