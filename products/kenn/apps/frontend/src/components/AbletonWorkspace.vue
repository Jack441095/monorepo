<template>
  <div class="mix-lab">
    <!-- Proactive Live Export / Bounce Watcher Alert Banner -->
    <transition name="fade">
      <div v-if="detectedBounce" class="mix-lab__bounce-alert" role="alert">
        <div class="mix-lab__bounce-alert-info">
          <span class="mix-lab__bounce-alert-badge">Live Export Detected</span>
          <strong>{{ detectedBounce.label }}</strong>
          <span class="mix-lab__bounce-alert-filename">({{ detectedBounce.filename }} • {{ formatSize(detectedBounce.size_bytes) }})</span>
        </div>
        <div class="mix-lab__bounce-alert-actions">
          <button
            type="button"
            class="mix-lab__bounce-btn mix-lab__bounce-btn--primary"
            :disabled="isBusy"
            @click="loadDetectedBounceAsMix"
          >
            Load as Mix & Analyse
          </button>
          <button
            type="button"
            class="mix-lab__bounce-btn"
            :disabled="isBusy"
            @click="loadDetectedBounceAsRef"
          >
            Set as Reference (A/B)
          </button>
          <button
            type="button"
            class="mix-lab__bounce-btn mix-lab__bounce-btn--dismiss"
            title="Dismiss notification"
            @click="detectedBounce = null"
          >
            ✕
          </button>
        </div>
      </div>
    </transition>

    <!-- Active Live Project Audio Bar -->
    <div class="mix-lab__project-bar">
      <div class="mix-lab__project-tag">
        <span class="mix-lab__project-badge">Ableton Project</span>
        <strong>{{ projectAudioInfo?.project_name || project.name || 'outer shell 2026-kenn-test' }}</strong>
      </div>

      <div class="mix-lab__source-select-wrap">
        <label for="project-audio-select" class="mix-lab__source-label">Mix Source:</label>
        <select
          id="project-audio-select"
          v-model="selectedBouncePath"
          class="mix-lab__source-select"
          :disabled="isBusy || scanningProject"
          @change="onBounceSelected"
        >
          <option value="" disabled>Select Master or Stem from Ableton project…</option>
          <optgroup v-if="masterBounces.length" label="Master Bounces">
            <option v-for="b in masterBounces" :key="b.path" :value="b.path">
              {{ b.label }} ({{ formatSize(b.size_bytes) }})
            </option>
          </optgroup>
          <optgroup v-if="stemBounces.length" label="Track Stems">
            <option v-for="b in stemBounces" :key="b.path" :value="b.path">
              {{ b.label }} ({{ formatSize(b.size_bytes) }})
            </option>
          </optgroup>
        </select>
      </div>

      <div class="mix-lab__source-select-wrap">
        <label for="project-audio-ref-select" class="mix-lab__source-label">Reference (A/B):</label>
        <select
          id="project-audio-ref-select"
          v-model="selectedRefBouncePath"
          class="mix-lab__source-select mix-lab__source-select--ref"
          :disabled="isBusy || scanningProject"
          @change="onRefBounceSelected"
        >
          <option value="">None (Upload or choose project audio…)</option>
          <optgroup v-if="masterBounces.length" label="Master Bounces">
            <option v-for="b in masterBounces" :key="'ref-'+b.path" :value="b.path">
              {{ b.label }} ({{ formatSize(b.size_bytes) }})
            </option>
          </optgroup>
          <optgroup v-if="stemBounces.length" label="Track Stems">
            <option v-for="b in stemBounces" :key="'ref-'+b.path" :value="b.path">
              {{ b.label }} ({{ formatSize(b.size_bytes) }})
            </option>
          </optgroup>
        </select>
      </div>

      <!-- Quick Jump Shortcuts to Masking Radar and Reference Matcher -->
      <div class="mix-lab__quick-nav">
        <button
          type="button"
          class="mix-lab__quick-nav-btn"
          :class="{ 'is-active': activeView === 'masking' }"
          title="Jump to Session Doctor & 40-Band Masking Radar"
          @click="activeView = 'masking'"
        >
          Masking Radar
        </button>
        <button
          type="button"
          class="mix-lab__quick-nav-btn"
          :class="{ 'is-active': activeView === 'reference' }"
          title="Jump to Commercial Reference Matcher (A/B)"
          @click="activeView = 'reference'"
        >
          Stem A/B Match
        </button>
      </div>

      <button
        type="button"
        class="mix-lab__scan-btn"
        :disabled="isBusy || scanningProject"
        title="Scan project folder for new bounces, stems, and renders from Live"
        @click="scanProjectAudio"
      >
        {{ scanningProject ? 'Scanning…' : '↻ Scan Project' }}
      </button>

      <span class="mix-lab__status" :data-state="status">● {{ t(`mixReview.${statusKey}`) }}</span>
    </div>

    <div class="mix-lab__inputs">
      <span class="mix-lab__inputs-label">{{ t('mixReview.inputs') }}</span>
      <label class="mix-lab__file">
        <input type="file" :accept="audioAccept" :disabled="isBusy" @change="onMixChange" />
        <strong><i class="mix-lab__req" aria-hidden="true">*</i>{{ t('mixReview.mixFile') }}</strong>
        <em>{{ mixFile?.name || t('mixReview.chooseWav') }}</em>
      </label>
      <label class="mix-lab__file">
        <input type="file" :accept="audioAccept" :disabled="isBusy" @change="onRefChange" />
        <strong>{{ t('mixReview.referenceFile') }}</strong>
        <em>{{ referenceFile?.name || t('mixReview.optional') }}</em>
      </label>
      <input v-model="title" class="mix-lab__field" type="text" :placeholder="t('mixReview.trackTitle')" :disabled="isBusy" />
      <input v-model="version" class="mix-lab__field mix-lab__field--sm" type="text" :placeholder="t('mixReview.version')" :disabled="isBusy" />
      <button
        type="button"
        class="mix-lab__primary"
        :class="{ 'is-disabled': analyzeDisabled }"
        :disabled="isBusy"
        :aria-disabled="analyzeDisabled || undefined"
        @click="onAnalyseClick"
      >
        {{ isBusy ? t('mixReview.analysing') : t('mixReview.analyse') }}
      </button>
    </div>

    <p v-if="useMock" class="mix-lab__mock-hint">{{ t('mixReview.mockHint') }}</p>
    <p v-if="errorMessage" class="mix-lab__error">{{ errorMessage }}</p>

    <nav class="mix-lab__tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :ref="(el) => setTabRef(tab.id, el)"
        type="button"
        class="mix-lab__tab"
        :class="{ 'is-active': activeView === tab.id }"
        @click="activeView = tab.id"
      >
        {{ t(tab.labelKey) }}
      </button>
    </nav>

    <!-- 每个视图独立容器 + FloatDetachable；v-show 打在单根包装上才能正确切换 -->
    <section class="mix-lab__stage">
      <div class="mix-lab__canvas">
        <div v-show="activeView === 'waveform'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.waveform"
            layout="fill"
            :enabled="canFloat"
            :title="t('mixReview.waveformAnalysis')"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>{{ t('mixReview.waveformAnalysis') }}</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <MixReviewWaveform
                class="mix-lab__view-chart"
                :peaks="activePeaks"
                :empty-text="t('mixReview.emptyWaveform')"
              />
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'bands'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.bands"
            layout="fill"
            :enabled="canFloat"
            :title="t('mixReview.spectralAnalysis')"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div class="mix-lab__view-head">
                <h3 v-if="!floating">{{ t('mixReview.spectralAnalysis') }}</h3>
                <div class="mix-lab__view-head-end">
                  <div class="mix-lab__spectrum-tools">
                    <div class="mix-lab__band-legend" aria-hidden="true">
                      <span data-status="ok"><i />{{ t('mixReview.bandLegendOk') }}</span>
                      <span data-status="warn"><i />{{ t('mixReview.bandLegendWarn') }}</span>
                      <span data-status="bad"><i />{{ t('mixReview.bandLegendBad') }}</span>
                    </div>
                    <div class="mix-lab__chips">
                      <button
                        v-for="m in bandModes"
                        :key="m.id"
                        type="button"
                        class="mix-lab__chip"
                        :class="{ 'is-active': bandMode === m.id }"
                        @click="bandMode = m.id"
                      >
                        {{ t(m.labelKey) }}
                      </button>
                    </div>
                  </div>
                  <button
                    v-if="showPop"
                    type="button"
                    class="mix-lab__pop-btn"
                    :disabled="!canPop"
                    @pointerdown.stop
                    @click="openFloat()"
                  >
                    {{ t('mixReview.floatOpen') }}
                  </button>
                </div>
              </div>
              <MixReviewBandChart
                class="mix-lab__view-chart"
                :mode="bandMode"
                :bands="bandMode === 'perceptual' ? metrics?.perceptual_bands : metrics?.bands"
                :log-bands="metrics?.log_bands_40"
                :alert-key="alertBand"
                :empty-text="t('mixReview.emptyBands')"
              />
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'timeline'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.timeline"
            layout="fill"
            :enabled="canFloat"
            :title="t('mixReview.timelineAnalysis')"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>{{ t('mixReview.timelineAnalysis') }}</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <MixReviewTimeline
                class="mix-lab__view-chart"
                :timeline="metrics?.correlation_timeline"
                :empty-text="t('mixReview.emptyTimeline')"
              />
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'metrics'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.metrics"
            layout="fill"
            :enabled="canFloat"
            :title="t('mixReview.metricsOverview')"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>{{ t('mixReview.metricsOverview') }}</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__metrics-grid mix-lab__view-chart">
                <div v-for="card in metricCards" :key="card.label" class="mix-lab__metric-card">
                  <strong>{{ card.value }}</strong>
                  <span>{{ card.label }}</span>
                </div>
                <p v-if="!metrics" class="mix-lab__empty">{{ t('mixReview.emptyMetrics') }}</p>
              </div>
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'reference'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.reference"
            layout="fill"
            :enabled="true"
            :title="t('mixReview.referenceTitle')"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>{{ t('mixReview.referenceTitle') }}</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__view-chart" style="overflow-y: auto; max-height: 520px; padding: 12px 16px;">
                <KennReferenceMatcher
                  :initial-mix-file="mixFile"
                  :initial-ref-file="referenceFile"
                />
              </div>
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'masking'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.masking"
            layout="fill"
            :enabled="true"
            title="Session Doctor & 40-Band Masking Radar"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>Session Doctor & Masking Radar</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__view-chart" style="height: 100%;">
                <MaskingRadar />
              </div>
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'racks'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.racks"
            layout="fill"
            :enabled="true"
            title="12 Pro Audio Effect Rack Synthesizers"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>12 Pro Audio Effect Racks</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__view-chart" style="height: 100%;">
                <ProRackGallery />
              </div>
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'midi'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.midi"
            layout="fill"
            :enabled="true"
            title="Neural MIDI Studio & AudioGen Groove Engine"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>Neural MIDI & AudioGen Groove Studio</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__view-chart" style="height: 100%;">
                <NeuralMidiStudio />
              </div>
            </div>
          </FloatDetachable>
        </div>

        <div v-show="activeView === 'classification'" class="mix-lab__view-host">
          <FloatDetachable
            v-model:open="viewOpen.classification"
            layout="fill"
            :enabled="true"
            title="SLO Classification Review"
            #default="{ openFloat, canPop, showPop, floating }"
          >
            <div class="mix-lab__view-pane">
              <div v-if="!floating" class="mix-lab__view-head">
                <h3>SLO Classification Review</h3>
                <button
                  v-if="showPop"
                  type="button"
                  class="mix-lab__pop-btn"
                  :disabled="!canPop"
                  @pointerdown.stop
                  @click="openFloat()"
                >
                  {{ t('mixReview.floatOpen') }}
                </button>
              </div>
              <div class="mix-lab__view-chart" style="height: 100%;">
                <SloClassificationPanel />
              </div>
            </div>
          </FloatDetachable>
        </div>
      </div>
    </section>

    <section class="mix-lab__results">
      <FloatDetachable
        layout="stretch"
        :enabled="canFloat"
        :title="t('mixReview.criticalFlags')"
        #default="{ openFloat, canPop, showPop, floating }"
      >
        <div class="mix-lab__flags">
          <div v-if="!floating" class="mix-lab__card-head">
            <h4>{{ t('mixReview.criticalFlags') }}</h4>
            <button
              v-if="showPop"
              type="button"
              class="mix-lab__pop-btn"
              :disabled="!canPop"
              @pointerdown.stop
              @click="openFloat()"
            >
              {{ t('mixReview.floatOpen') }}
            </button>
          </div>
          <div class="mix-lab__card-body">
            <div class="mix-lab__card-main">
              <ul v-if="review?.flags?.length">
                <li v-for="(flag, i) in review.flags" :key="i" :data-severity="flag.severity || 'low'">
                  <i />
                  <strong>{{ flag.label }}</strong>
                  <button
                    type="button"
                    class="mix-lab__fix-btn"
                    :disabled="sending"
                    :title="`Ask KENN to formulate a Live 12 proposal for ${flag.label}`"
                    @click="askKennToFix(flag)"
                  >
                    Ask KENN to Fix
                  </button>
                </li>
              </ul>
              <p v-else class="mix-lab__empty-sm">
                {{ review ? t('mixReview.noFlags') : '' }}
              </p>
            </div>
            <div v-if="review?.flags?.length" class="mix-lab__card-foot">
              <p v-for="(flag, i) in review.flags" :key="`d-${i}`">{{ flag.detail }}</p>
              <button
                type="button"
                class="mix-lab__remediate-all-btn"
                :disabled="sending"
                @click="askKennToFixAll"
              >
                Propose Live 12 Fix Recipe for All Flags
              </button>
            </div>
          </div>
        </div>
      </FloatDetachable>

      <FloatDetachable
        layout="stretch"
        :enabled="canFloat"
        :title="t('mixReview.auditSummary')"
        #default="{ openFloat, canPop, showPop, floating }"
      >
        <div class="mix-lab__summary">
          <div v-if="!floating" class="mix-lab__card-head">
            <h4>{{ t('mixReview.auditSummary') }}</h4>
            <button
              v-if="showPop"
              type="button"
              class="mix-lab__pop-btn"
              :disabled="!canPop"
              @pointerdown.stop
              @click="openFloat()"
            >
              {{ t('mixReview.floatOpen') }}
            </button>
          </div>
          <div class="mix-lab__card-body">
            <div class="mix-lab__card-main">
              <p>{{ review?.summary || '' }}</p>
            </div>
            <ul v-if="review?.advice?.length" class="mix-lab__card-foot mix-lab__advice">
              <li v-for="(line, i) in review.advice" :key="i">{{ line }}</li>
            </ul>
            <button
              v-if="review?.next_step"
              type="button"
              class="mix-lab__ask"
              :disabled="sending"
              @click="sendMessage(review.next_step.say)"
            >
              {{ t('mixReview.askKenn') }}: “{{ review.next_step.say }}”
            </button>
            <button
              v-else-if="review?.flags?.length"
              type="button"
              class="mix-lab__remediate-all-btn"
              :disabled="sending"
              @click="askKennToFixAll"
            >
              Propose Live 12 Fix Recipe for All Flags
            </button>
          </div>
        </div>
      </FloatDetachable>

      <FloatDetachable
        layout="stretch"
        :enabled="canFloat"
        :title="t('mixReview.overallScore')"
        #default="{ openFloat, canPop, showPop, floating }"
      >
        <div class="mix-lab__score-col">
          <div v-if="!floating" class="mix-lab__card-head">
            <h4>{{ t('mixReview.overallScore') }}</h4>
            <button
              v-if="showPop"
              type="button"
              class="mix-lab__pop-btn"
              :disabled="!canPop"
              @pointerdown.stop
              @click="openFloat()"
            >
              {{ t('mixReview.floatOpen') }}
            </button>
          </div>
          <div class="mix-lab__card-body">
            <div class="mix-lab__card-main">
              <div class="mix-lab__score">
                <strong>{{ metrics?.technical_score ?? '—' }}</strong>
                <span>/ 100</span>
              </div>
              <div v-if="review?.comparison" class="mix-lab__delta">
                <h5>{{ t('mixReview.referenceComparison') }}</h5>
                <MixReviewBandChart :bands="review.comparison.band_delta || {}" mode="raw" />
              </div>
            </div>
            <div class="mix-lab__card-foot">
              <div v-if="metrics?.technical_rating" class="mix-lab__rating">{{ metrics.technical_rating }}</div>
              <p v-if="review?.comparison">
                {{
                  t('mixReview.comparisonDelta', {
                    rms: fmt(review.comparison.rms_delta_db),
                    crest: fmt(review.comparison.crest_delta_db),
                  })
                }}
              </p>
            </div>
          </div>
        </div>
      </FloatDetachable>
    </section>

    <div v-if="isBusy" class="mix-lab__modal" role="dialog" aria-modal="true" :aria-label="t('mixReview.analysing')">
      <div class="mix-lab__modal-backdrop" />
      <div class="mix-lab__modal-card">
        <button
          type="button"
          class="mix-lab__modal-close"
          :aria-label="t('mixReview.cancelAnalyse')"
          @click="cancelAnalyze"
        >
          ×
        </button>
        <div class="mix-lab__modal-spinner" aria-hidden="true" />
        <strong>{{ t('mixReview.analysing') }}</strong>
        <span>{{ t('mixReview.analysingHint') }}</span>
        <button type="button" class="mix-lab__modal-cancel" @click="cancelAnalyze">
          {{ t('mixReview.cancelAnalyse') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FloatDetachable from './common/FloatDetachable.vue'
import MixReviewBandChart from './mix-review/MixReviewBandChart.vue'
import MixReviewTimeline from './mix-review/MixReviewTimeline.vue'
import MixReviewWaveform from './mix-review/MixReviewWaveform.vue'
import KennReferenceMatcher from './KennReferenceMatcher.vue'
import MaskingRadar from './studio/MaskingRadar.vue'
import ProRackGallery from './studio/ProRackGallery.vue'
import NeuralMidiStudio from './studio/NeuralMidiStudio.vue'
import SloClassificationPanel from './studio/SloClassificationPanel.vue'
import { useMixReview } from '../composables/useMixReview'
import { useKenn } from '../composables/useKenn'
import { showToast } from '../composables/useToast'
import { isLikelyMixAudio, MIX_REVIEW_AUDIO_ACCEPT } from '../utils/audioFormats'
import type { MixReviewView } from '../utils/mixReviewTypes'

const audioAccept = MIX_REVIEW_AUDIO_ACCEPT

const { t } = useI18n()
const {
  mixFile,
  referenceFile,
  title,
  version,
  useMock,
  status,
  statusKey,
  errorKey,
  errorDetail,
  review,
  decoded,
  activeView,
  bandMode,
  isBusy,
  metrics,
  checkSession,
  setMixFile,
  setReferenceFile,
  analyze,
  cancelAnalyze,
} = useMixReview()
const { sendMessage, sending, project } = useKenn()

type ProjectBounce = {
  filename: string
  label: string
  kind: 'master' | 'stem'
  path: string
  size_bytes: number
  modified_time: number
  is_main_bounce: boolean
}

const projectAudioInfo = ref<{
  project_name?: string
  project_dir?: string
  als_path?: string
} | null>(null)

const projectBounces = ref<ProjectBounce[]>([])
const selectedBouncePath = ref<string>('')
const selectedRefBouncePath = ref<string>('')
const scanningProject = ref<boolean>(false)

// Proactive Live export detection state
const latestBounceMtime = ref<number>(0)
const detectedBounce = ref<ProjectBounce | null>(null)
let bouncePollTimer: ReturnType<typeof setInterval> | null = null

const masterBounces = computed(() => projectBounces.value.filter((b) => b.kind === 'master'))
const stemBounces = computed(() => projectBounces.value.filter((b) => b.kind === 'stem'))

function formatSize(bytes: number) {
  if (!bytes) return ''
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB`
}

async function scanProjectAudio() {
  scanningProject.value = true
  try {
    const base = import.meta.env.VITE_KENN_API_BASE ?? ''
    const res = await fetch(`${base}/api/ableton/project-audio`)
    if (!res.ok) return
    const data = await res.json()
    if (data.ok) {
      projectAudioInfo.value = {
        project_name: data.project_name,
        project_dir: data.project_dir,
        als_path: data.als_path,
      }
      projectBounces.value = Array.isArray(data.bounces) ? data.bounces : []
      if (projectBounces.value.length > 0 && latestBounceMtime.value === 0) {
        latestBounceMtime.value = Math.max(...projectBounces.value.map((b) => b.modified_time), 0)
      }
    }
  } catch {
    // Graceful offline degradation
  } finally {
    scanningProject.value = false
  }
}

async function pollForNewBounces() {
  if (scanningProject.value) return
  try {
    const base = import.meta.env.VITE_KENN_API_BASE ?? ''
    const res = await fetch(`${base}/api/ableton/project-audio/poll?since=${latestBounceMtime.value}`)
    if (!res.ok) return
    const data = await res.json()
    if (data.ok) {
      if (typeof data.latest_mtime === 'number' && data.latest_mtime > 0) {
        latestBounceMtime.value = data.latest_mtime
      }
      if (data.has_new && data.new_bounce) {
        detectedBounce.value = data.new_bounce
        void scanProjectAudio()
        showToast(`New Live bounce detected: ${data.new_bounce.label}`, 'info')
      }
    }
  } catch {
    // Graceful offline degradation
  }
}

async function loadDetectedBounceAsMix() {
  if (!detectedBounce.value) return
  const bounce = detectedBounce.value
  detectedBounce.value = null
  selectedBouncePath.value = bounce.path
  await onBounceSelected()
}

async function loadDetectedBounceAsRef() {
  if (!detectedBounce.value) return
  const bounce = detectedBounce.value
  detectedBounce.value = null
  selectedRefBouncePath.value = bounce.path
  await onRefBounceSelected()
}

async function onRefBounceSelected() {
  if (!selectedRefBouncePath.value) {
    setReferenceFile(null)
    return
  }
  const bounce = projectBounces.value.find((b) => b.path === selectedRefBouncePath.value)
  if (!bounce) return

  try {
    const base = import.meta.env.VITE_KENN_API_BASE ?? ''
    const res = await fetch(`${base}/api/ableton/project-audio/file?path=${encodeURIComponent(bounce.path)}`)
    if (!res.ok) throw new Error('Failed to fetch reference audio bounce')
    const blob = await res.blob()
    const file = new File([blob], bounce.filename, { type: 'audio/wav' })
    setReferenceFile(file)
    showToast(`Reference audio set to ${bounce.label}`, 'success')
  } catch (e) {
    console.error('Error loading reference bounce:', e)
  }
}

function askKennToFix(flag: { label?: string; detail?: string }) {
  const label = flag.label || 'issue'
  const detail = flag.detail || ''
  const lower = label.toLowerCase()
  let prompt = `Fix ${label} in Live 12`

  if (lower.includes('mask') || lower.includes('mud') || lower.includes('sub') || lower.includes('clash')) {
    prompt = `Fix the masking clashes and low end mud in Live 12: ${detail || label}`
  } else if (lower.includes('clip') || lower.includes('headroom') || lower.includes('peak') || lower.includes('crest')) {
    prompt = `Fix clipping risk and reclaim summing headroom in Live 12: ${detail || label}`
  } else if (lower.includes('phase') || lower.includes('mono') || lower.includes('width') || lower.includes('correlation')) {
    prompt = `Fix phase correlation and mono compatibility issues in Live 12: ${detail || label}`
  } else if (lower.includes('sibil') || lower.includes('harsh') || lower.includes('air') || lower.includes('high')) {
    prompt = `Fix harsh high frequencies and sibilance in Live 12: ${detail || label}`
  } else {
    prompt = `Fix ${label} in Live 12: ${detail || ''}`
  }

  showToast(`Routing "${label}" to KENN to formulate Live 12 proposal…`, 'info')
  void sendMessage(prompt.trim())
}

function askKennToFixAll() {
  showToast('Consulting KENN to formulate atomic Live 12 remedy recipe…', 'info')
  void sendMessage('Propose fixes in Live 12 for all masking, clipping, and phase issues')
}

async function onBounceSelected() {
  if (!selectedBouncePath.value) return
  const bounce = projectBounces.value.find((b) => b.path === selectedBouncePath.value)
  if (!bounce) return

  try {
    const base = import.meta.env.VITE_KENN_API_BASE ?? ''
    const res = await fetch(`${base}/api/ableton/project-audio/file?path=${encodeURIComponent(bounce.path)}`)
    if (!res.ok) throw new Error('Failed to fetch audio bounce')
    const blob = await res.blob()
    const file = new File([blob], bounce.filename, { type: 'audio/wav' })
    setMixFile(file)
    const projName = projectAudioInfo.value?.project_name || project.value.name || 'outer shell 2026-kenn-test'
    title.value = `${projName} — ${bounce.label}`
    version.value = bounce.kind === 'master' ? 'Master' : 'Stem'
    await analyze()
  } catch (e) {
    console.error('Error loading project bounce:', e)
  }
}

/** Returns decoded audio peaks from client Web Audio or server-measured peaks from Mix Review metrics */
const activePeaks = computed<Float32Array | null>(() => {
  if (decoded.value?.peaks && decoded.value.peaks.length > 0) return decoded.value.peaks
  if (metrics.value?.peaks && Array.isArray(metrics.value.peaks) && metrics.value.peaks.length > 0) {
    return new Float32Array(metrics.value.peaks)
  }
  return null
})

const tabs: Array<{ id: MixReviewView; labelKey: string }> = [
  { id: 'waveform', labelKey: 'mixReview.viewWaveform' },
  { id: 'bands', labelKey: 'mixReview.viewBands' },
  { id: 'masking', labelKey: 'mixReview.viewMasking' },
  { id: 'racks', labelKey: 'mixReview.viewRacks' },
  { id: 'midi', labelKey: 'mixReview.viewMidi' },
  { id: 'classification', labelKey: 'mixReview.viewClassification' },
  { id: 'timeline', labelKey: 'mixReview.viewTimeline' },
  { id: 'metrics', labelKey: 'mixReview.viewMetrics' },
  { id: 'reference', labelKey: 'mixReview.viewReference' },
]

const bandModes = [
  { id: 'raw' as const, labelKey: 'mixReview.bandRaw' },
  { id: 'perceptual' as const, labelKey: 'mixReview.bandPerceptual' },
  { id: 'log40' as const, labelKey: 'mixReview.bandLog40' },
]

const tabEls = ref<Partial<Record<MixReviewView, HTMLElement>>>({})

/** 各视图弹窗独立开关，可同时存在 */
const viewOpen = reactive({
  waveform: false,
  bands: false,
  masking: false,
  racks: false,
  midi: false,
  timeline: false,
  metrics: false,
  reference: false,
  classification: false,
})

/** 仅分析完成且有结果时允许弹出 */
const canFloat = computed(() => status.value === 'completed' && !!review.value)

function setTabRef(id: MixReviewView, el: unknown) {
  if (el && el instanceof HTMLElement) tabEls.value[id] = el
  else delete tabEls.value[id]
}

const errorMessage = computed(() => {
  if (errorKey.value) return t(`mixReview.${errorKey.value}`)
  return errorDetail.value
})

const alertBand = computed(() => {
  const label = review.value?.flags?.[0]?.label?.toLowerCase() || ''
  if (label.includes('sibil')) return 'sibilance'
  if (label.includes('sub') || label.includes('low end') || label.includes('bass')) return 'bass'
  return ''
})

function fmt(v: unknown, digits = 2) {
  if (v === undefined || v === null || v === '' || v === 'n/a') return '—'
  const n = Number(v)
  return Number.isNaN(n) ? String(v) : n.toFixed(digits)
}

const metricCards = computed(() => {
  const m = metrics.value
  if (!m) return []
  return [
    { label: t('mixReview.metricPeak'), value: fmt(m.peak_dbfs) },
    { label: t('mixReview.metricRms'), value: fmt(m.rms_dbfs_estimate) },
    { label: t('mixReview.metricLufs'), value: fmt(m.integrated_lufs) },
    { label: t('mixReview.metricCrest'), value: fmt(m.crest_factor_db) },
    { label: t('mixReview.metricTruePeak'), value: fmt(m.true_peak_dbfs) },
    { label: t('mixReview.metricCorrelation'), value: fmt(m.stereo_correlation, 3) },
    { label: t('mixReview.metricWidth'), value: fmt(m.stereo_width_ratio, 3) },
    {
      label: t('mixReview.metricClipping'),
      value: m.clipping_risk ? t('mixReview.riskYes') : t('mixReview.riskNo'),
    },
  ]
})

/** 真接口未选混音文件时视觉置灰，但仍可点击以 toast 提示 */
const analyzeDisabled = computed(() => !useMock.value && !mixFile.value)

function onAnalyseClick() {
  if (isBusy.value) return
  if (analyzeDisabled.value) {
    showToast(t('mixReview.errChooseWav'), 'error')
    return
  }
  void analyze()
}

function onMixChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) {
    setMixFile(null)
    return
  }
  if (!isLikelyMixAudio(file)) {
    showToast(t('mixReview.toastInvalidWav'), 'error')
    input.value = ''
    return
  }
  selectedBouncePath.value = ''
  setMixFile(file)
}

function onRefChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) {
    setReferenceFile(null)
    return
  }
  if (!isLikelyMixAudio(file)) {
    showToast(t('mixReview.toastInvalidWav'), 'error')
    input.value = ''
    return
  }
  setReferenceFile(file)
}

onMounted(async () => {
  void checkSession()
  await scanProjectAudio()
  if (projectBounces.value.length > 0) {
    latestBounceMtime.value = Math.max(...projectBounces.value.map((b) => b.modified_time), 0)
  }
  // Automatically select the master bounce from the active Ableton project if present
  if (!mixFile.value && masterBounces.value.length > 0) {
    selectedBouncePath.value = masterBounces.value[0].path
    void onBounceSelected()
  }
  // Periodically check for newly exported Live bounces (Cmd+Shift+R)
  bouncePollTimer = setInterval(() => {
    void pollForNewBounces()
  }, 3500)
})

onBeforeUnmount(() => {
  if (bouncePollTimer) {
    clearInterval(bouncePollTimer)
    bouncePollTimer = null
  }
})
</script>

<style scoped lang="less">
.mix-lab {
  --mr-accent: var(--workspace-accent);
  --mr-ok: #1f8a5a;
  --mr-warn: #a05a28;
  --mr-bad: #c0392b;
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0.14rem 0.16rem 0.12rem;
  gap: 0.1rem;
  background: var(--workspace-bg);
  overflow: auto;

  /* Teleport 到 body 后脱离 .mix-lab，需在弹出根上自带色板 */
  &__flags,
  &__summary,
  &__score-col,
  &__view-pane {
    --mr-accent: var(--workspace-accent);
    --mr-ok: #1f8a5a;
    --mr-warn: #a05a28;
    --mr-bad: #c0392b;
  }

  &__bounce-alert {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.12rem;
    padding: 0.08rem 0.14rem;
    background: linear-gradient(90deg, rgba(55, 214, 122, 0.15), rgba(22, 27, 34, 0.95));
    border: 1px solid #37d67a;
    border-radius: 0.08rem;
    box-shadow: 0 0 16px rgba(55, 214, 122, 0.18);
    flex-wrap: wrap;
  }

  &__bounce-alert-info {
    display: flex;
    align-items: center;
    gap: 0.08rem;
    font-size: 0.12rem;
    color: var(--text-color);
  }

  &__bounce-alert-badge {
    padding: 0.02rem 0.06rem;
    background: #37d67a;
    color: #0d1117;
    font-size: 0.10rem;
    font-weight: 800;
    border-radius: 0.04rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  &__bounce-alert-filename {
    color: var(--muted-text);
    font-size: 0.11rem;
  }

  &__bounce-alert-actions {
    display: flex;
    align-items: center;
    gap: 0.08rem;
  }

  &__bounce-btn {
    padding: 0.04rem 0.09rem;
    background: var(--floating-bg);
    border: 1px solid var(--floating-border);
    border-radius: 0.05rem;
    color: var(--text-color);
    font-size: 0.11rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s ease;

    &:hover:not(:disabled) {
      border-color: #37d67a;
      color: #37d67a;
    }

    &--primary {
      background: #37d67a;
      border-color: #37d67a;
      color: #0d1117;
      font-weight: 700;

      &:hover:not(:disabled) {
        background: #2ebd67;
        color: #0d1117;
      }
    }

    &--dismiss {
      background: transparent;
      border: none;
      color: var(--muted-text);
      font-size: 0.13rem;
      padding: 0.04rem 0.06rem;

      &:hover {
        color: #c0392b;
      }
    }
  }

  &__project-bar {
    display: flex;
    align-items: center;
    gap: 0.12rem;
    padding: 0.08rem 0.14rem;
    background: color-mix(in srgb, var(--workspace-panel) 90%, #0d1117);
    border: 1px solid var(--floating-border);
    border-radius: 0.08rem;
    flex-wrap: wrap;
  }

  &__project-tag {
    display: flex;
    align-items: center;
    gap: 0.08rem;
    font-size: 0.13rem;
    color: var(--text-color);
  }

  &__project-badge {
    padding: 0.02rem 0.06rem;
    background: color-mix(in srgb, #37d67a 20%, transparent);
    border: 1px solid rgba(55, 214, 122, 0.4);
    border-radius: 0.04rem;
    color: #37d67a;
    font-size: 0.10rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  &__source-select-wrap {
    display: flex;
    align-items: center;
    gap: 0.08rem;
  }

  &__source-label {
    font-size: 0.12rem;
    color: var(--muted-text);
    font-weight: 600;
  }

  &__source-select {
    padding: 0.05rem 0.1rem;
    background: var(--floating-bg);
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    color: var(--text-color);
    font-size: 0.12rem;
    font-weight: 600;
    min-width: 2.1rem;
    cursor: pointer;

    &:focus {
      outline: none;
      border-color: #37d67a;
    }

    optgroup {
      background: #161b22;
      color: #37d67a;
      font-weight: 700;
    }

    option {
      background: #0d1117;
      color: var(--text-color);
    }

    &--ref {
      border-color: color-mix(in srgb, var(--floating-border) 80%, #ffd700);
    }
  }

  &__quick-nav {
    display: flex;
    align-items: center;
    gap: 0.06rem;
    margin-left: 0.04rem;
  }

  &__quick-nav-btn {
    padding: 0.04rem 0.08rem;
    background: color-mix(in srgb, var(--floating-bg) 70%, #000);
    border: 1px solid var(--floating-border);
    border-radius: 0.05rem;
    color: var(--muted-text);
    font-size: 0.11rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s ease;

    &:hover,
    &.is-active {
      border-color: #37d67a;
      color: #37d67a;
      background: color-mix(in srgb, #37d67a 10%, var(--floating-bg));
    }
  }

  &__scan-btn {
    padding: 0.05rem 0.1rem;
    margin-left: auto;
    background: color-mix(in srgb, var(--floating-bg) 80%, #000);
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    color: var(--text-color);
    font-size: 0.11rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      border-color: #37d67a;
      color: #37d67a;
    }
  }

  &__inputs {
    --mr-card-w: 1.8rem;
    --mr-card-h: 0.52rem;
    display: flex;
    flex-wrap: nowrap;
    align-items: stretch;
    gap: 0.1rem;
    padding: 0.12rem;
    background: var(--workspace-panel);
    border: 1px solid var(--floating-border);
    border-radius: 0.1rem;
    overflow-x: auto;
    white-space: nowrap;
  }

  &__inputs-label {
    display: flex;
    align-items: center;
    flex: 0 0 auto;
    font-size: 0.12rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--text-color);
    margin-right: 0.02rem;
    padding: 0 0.04rem;
    white-space: nowrap;
  }

  &__req {
    margin-right: 0.02rem;
    font-style: normal;
    font-weight: 700;
    color: var(--mr-bad, #c0392b);
  }

  &__file {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.04rem;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    padding: 0.06rem 0.1rem;
    background: var(--workspace-panel-muted);
    border-radius: 0.08rem;
    cursor: pointer;
    overflow: hidden;
    input {
      display: none;
    }
    strong {
      font-size: 0.11rem;
      color: var(--muted-text);
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    em {
      font-style: normal;
      font-size: 0.14rem;
      font-weight: 500;
      color: var(--text-color);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  &__field {
    box-sizing: border-box;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    padding: 0 0.12rem;
    border: 1px solid var(--input-border);
    border-radius: 0.08rem;
    background: var(--workspace-field);
    color: var(--text-color);
    font-size: 0.14rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    outline: none;
    transition: border-color 0.15s ease;

    &:focus {
      border-color: color-mix(in srgb, var(--workspace-accent) 55%, transparent);
      outline: none;
      box-shadow: none;
    }

    &--sm {
      flex: 0 0 var(--mr-card-w);
      width: var(--mr-card-w);
      min-width: var(--mr-card-w);
      max-width: var(--mr-card-w);
    }
  }

  &__status {
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    font-size: 0.13rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 0 0.1rem;
    border-radius: 0.08rem;
    background: color-mix(in srgb, var(--text-color) 6%, transparent);
    color: var(--muted-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    &[data-state='completed'] {
      background: rgba(50, 209, 143, 0.16);
      color: var(--mr-ok);
    }
    &[data-state='failed'] {
      background: rgba(255, 109, 111, 0.16);
      color: var(--mr-bad);
    }
    &[data-state='uploading'],
    &[data-state='processing'] {
      background: color-mix(in srgb, var(--workspace-accent) 12%, transparent);
      color: var(--mr-accent);
    }
  }

  &__primary {
    box-sizing: border-box;
    margin-left: auto;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    padding: 0 0.1rem;
    border: none;
    border-radius: 0.08rem;
    background: var(--mr-accent);
    color: var(--workspace-accent-text);
    font-size: 0.14rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    &:disabled,
    &.is-disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }

  &__sync-btn {
    box-sizing: border-box;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    padding: 0 0.1rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.08rem;
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-color);
    font-size: 0.13rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: background 0.2s, border-color 0.2s;
    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.12);
      border-color: var(--mr-accent);
    }
    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }

  &__ghost {
    box-sizing: border-box;
    flex: 0 0 var(--mr-card-w);
    width: var(--mr-card-w);
    min-width: var(--mr-card-w);
    max-width: var(--mr-card-w);
    min-height: var(--mr-card-h);
    height: var(--mr-card-h);
    padding: 0 0.1rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.08rem;
    background: var(--workspace-panel);
    color: var(--text-color);
    font-size: 0.14rem;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__mock-hint {
    margin: 0;
    font-size: 0.13rem;
    color: var(--mr-accent);
  }

  &__error {
    margin: 0;
    font-size: 0.14rem;
    color: var(--mr-bad);
  }

  &__tabs {
    display: flex;
    gap: 0.04rem;
    border-bottom: 1px solid var(--floating-border);
    user-select: none;
  }

  &__tab {
    border: none;
    background: transparent;
    padding: 0.1rem 0.16rem;
    font-size: 0.15rem;
    color: var(--muted-text);
    cursor: pointer;
    border-bottom: 0.02rem solid transparent;
    &.is-active {
      color: var(--mr-accent);
      font-weight: 600;
      border-bottom-color: var(--mr-accent);
    }
  }

  &__stage {
    /* 高度仍由父级 flex 分配，与套 FloatDetachable 前一致 */
    flex: 1;
    min-height: 2.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.08rem;
    padding: 0.12rem;
    background: var(--workspace-panel);
    border: 1px solid var(--floating-border);
    border-radius: 0.1rem;
  }

  &__view-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.1rem;
    flex-shrink: 0;
    h3 {
      margin: 0;
      font-size: 0.15rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted-text);
    }
  }

  &__view-head-end {
    display: flex;
    align-items: center;
    gap: 0.1rem;
    flex-wrap: wrap;
    justify-content: flex-end;
    min-width: 0;
  }

  &__card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.08rem;
    flex-shrink: 0;
    h4 {
      margin: 0;
    }
  }

  &__pop-btn {
    flex-shrink: 0;
    margin: 0;
    padding: 0.04rem 0.1rem;
    border: none;
    border-radius: 0.06rem;
    background: color-mix(in srgb, var(--text-color) 6%, transparent);
    color: var(--muted-text);
    font-size: 0.12rem;
    line-height: 1.4;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s ease, color 0.15s ease, opacity 0.15s ease;

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--text-color) 12%, transparent);
      color: var(--text-color);
    }

    &:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
  }

  &__spectrum-tools {
    display: flex;
    align-items: center;
    gap: 0.14rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  &__band-legend {
    display: flex;
    align-items: center;
    gap: 0.1rem;
    span {
      display: inline-flex;
      align-items: center;
      gap: 0.04rem;
      font-size: 0.12rem;
      color: var(--muted-text);
      white-space: nowrap;
    }
    i {
      width: 0.1rem;
      height: 0.1rem;
      border-radius: 50%;
      flex-shrink: 0;
    }
    [data-status='ok'] i {
      background: #1f8a5a;
    }
    [data-status='warn'] i {
      background: #c47b4a;
    }
    [data-status='bad'] i {
      background: #c0392b;
    }
  }

  &__chips {
    display: flex;
    gap: 0.06rem;
  }

  &__chip {
    border: 1px solid var(--floating-border);
    background: var(--workspace-panel);
    border-radius: 999px;
    padding: 0.06rem 0.12rem;
    font-size: 0.13rem;
    letter-spacing: 0.04em;
    color: var(--muted-text);
    cursor: pointer;
    &.is-active {
      background: var(--mr-accent);
      border-color: var(--mr-accent);
      color: var(--workspace-accent-text);
    }
  }

  &__canvas {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }

  &__view-host {
    flex: 1;
    min-height: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  &__view-pane {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    gap: 0.08rem;
  }

  &__view-chart {
    flex: 1;
    min-height: 0;
  }

  &__metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(1.1rem, 1fr));
    gap: 0.08rem;
    height: 100%;
    align-content: start;
  }

  &__metric-card {
    padding: 0.12rem;
    background: var(--workspace-panel-muted);
    border-radius: 0.08rem;
    strong {
      display: block;
      font-size: 0.18rem;
    }
    span {
      font-size: 0.13rem;
      color: var(--muted-text);
    }
  }

  &__empty,
  &__empty-sm {
    margin: 0.2rem 0 0;
    font-size: 0.14rem;
    color: var(--muted-text);
    text-align: center;
  }
  &__empty {
    white-space: nowrap;
  }
  &__empty-sm {
    text-align: left;
    margin-top: 0.08rem;
  }

  &__results {
    display: grid;
    grid-template-columns: 0.85fr 1fr 1.25fr;
    gap: 0.1rem;
    height: 3.1rem;
    min-height: 3.1rem;
    max-height: 3.1rem;
    flex: 0 0 3.1rem;
  }

  &__flags,
  &__summary,
  &__score-col {
    display: flex;
    flex-direction: column;
    background: var(--workspace-panel);
    border: 1px solid var(--floating-border);
    border-radius: 0.1rem;
    padding: 0.1rem 0.12rem;
    height: 100%;
    min-height: 0;
    max-height: none;
    overflow: hidden;
    h4,
    h5 {
      margin: 0 0 0.06rem;
      flex-shrink: 0;
      font-size: 0.13rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted-text);
    }
    .mix-lab__card-head {
      margin-bottom: 0.06rem;
      h4 {
        margin: 0;
      }
    }
    p {
      margin: 0;
      font-size: 0.13rem;
      line-height: 1.4;
      color: var(--text-color);
    }
  }

  &__card-body {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
  }

  &__card-main {
    flex: 1 0 auto;
    min-height: 0;
  }

  &__card-foot {
    flex-shrink: 0;
    margin-top: auto;
    padding-top: 0.1rem;
    border-top: 1px solid var(--floating-border);
    font-size: 0.12rem;
    color: var(--muted-text);
    line-height: 1.35;
    p + p {
      margin-top: 0.04rem;
    }
  }

  &__flags ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.06rem;
    li {
      display: flex;
      align-items: center;
      gap: 0.08rem;
      i {
        display: block;
        width: 0.04rem;
        height: 0.16rem;
        border-radius: 999px;
        background: #9aa3ad;
        flex-shrink: 0;
      }
      &[data-severity='high'] i {
        background: var(--mr-bad, #c0392b);
      }
      &[data-severity='medium'] i {
        background: var(--mr-warn, #a05a28);
      }
      strong {
        font-size: 0.14rem;
      }
      .mix-lab__fix-btn {
        margin-left: auto;
        padding: 0.03rem 0.07rem;
        background: color-mix(in srgb, #37d67a 15%, transparent);
        border: 1px solid rgba(55, 214, 122, 0.4);
        border-radius: 0.04rem;
        color: #37d67a;
        font-size: 0.10rem;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.15s ease;

        &:hover:not(:disabled) {
          background: #37d67a;
          color: #0d1117;
          box-shadow: 0 0 8px rgba(55, 214, 122, 0.3);
        }
      }
    }
  }

  &__remediate-all-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.06rem;
    padding: 0.06rem 0.12rem;
    margin-top: 0.08rem;
    background: linear-gradient(135deg, rgba(55, 214, 122, 0.2), rgba(55, 214, 122, 0.06));
    border: 1px solid rgba(55, 214, 122, 0.5);
    border-radius: 0.06rem;
    color: #37d67a;
    font-size: 0.11rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background: #37d67a;
      color: #0d1117;
      box-shadow: 0 0 12px rgba(55, 214, 122, 0.35);
    }
  }

  &__ask {
    align-self: flex-start;
    margin: 0.08rem 0 0;
    padding: 0.06rem 0.12rem;
    border: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
    border-radius: 0.06rem;
    background: color-mix(in srgb, var(--text-color) 6%, transparent);
    color: var(--text-color);
    font-size: 0.12rem;
    line-height: 1.4;
    text-align: left;
    cursor: pointer;

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--text-color) 12%, transparent);
    }

    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }

  &__advice {
    margin: 0;
    padding: 0.1rem 0 0 0.14rem;
    font-size: 0.12rem;
    color: var(--muted-text);
    line-height: 1.4;
  }

  &__score {
    display: flex;
    align-items: baseline;
    gap: 0.04rem;
    strong {
      font-size: 0.4rem;
      line-height: 1;
      color: var(--text-color);
    }
    span {
      font-size: 0.16rem;
      color: var(--muted-text);
    }
  }

  &__rating {
    display: inline-block;
    padding: 0.04rem 0.1rem;
    border-radius: 0.06rem;
    background: rgba(50, 209, 143, 0.16);
    color: var(--mr-ok);
    font-size: 0.13rem;
    font-weight: 600;
  }

  &__delta {
    margin-top: 0.08rem;
    min-height: 0;
    :deep(.mr-bands) {
      min-height: 0.9rem;
    }
  }

  &__score-col .mix-lab__card-foot p {
    margin-top: 0.06rem;
    font-size: 0.12rem;
    color: var(--muted-text);
  }

  &__modal {
    position: absolute;
    inset: 0;
    z-index: 40;
    display: grid;
    place-items: center;
    pointer-events: auto;
  }

  &__modal-backdrop {
    position: absolute;
    inset: 0;
    background: var(--workspace-overlay);
    backdrop-filter: blur(2px);
  }

  &__modal-card {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.08rem;
    min-width: 2.4rem;
    max-width: 80%;
    padding: 0.32rem 0.36rem 0.24rem;
    background: var(--workspace-panel);
    border: 1px solid var(--floating-border);
    border-radius: 0.12rem;
    box-shadow: 0 0.12rem 0.4rem rgba(15, 23, 42, 0.18);
    text-align: center;

    strong {
      font-size: 0.16rem;
      color: var(--text-color);
    }
    span {
      font-size: 0.12rem;
      color: var(--muted-text);
    }
  }

  &__modal-close {
    position: absolute;
    top: 0.06rem;
    right: 0.1rem;
    width: 0.28rem;
    height: 0.28rem;
    border: none;
    background: transparent;
    color: var(--muted-text);
    font-size: 0.22rem;
    line-height: 1;
    cursor: pointer;
    &:hover {
      color: var(--text-color);
    }
  }

  &__modal-cancel {
    margin-top: 0.06rem;
    min-height: 0.36rem;
    padding: 0 0.18rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    background: var(--workspace-panel);
    font-size: 0.13rem;
    color: var(--text-color);
    cursor: pointer;
    &:hover {
      background: var(--workspace-panel-muted);
    }
  }

  &__modal-spinner {
    width: 0.36rem;
    height: 0.36rem;
    margin-bottom: 0.04rem;
    border: 0.03rem solid color-mix(in srgb, var(--text-color) 12%, transparent);
    border-top-color: var(--workspace-accent);
    border-radius: 50%;
    animation: mix-lab-spin 0.8s linear infinite;
  }
}

@keyframes mix-lab-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .mix-lab__results {
    grid-template-columns: 1fr;
  }
}
</style>
