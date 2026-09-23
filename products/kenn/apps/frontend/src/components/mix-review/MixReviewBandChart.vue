<template>
  <div class="mr-bands">
    <template v-if="hasData">
      <div v-if="mode === 'log40'" class="mr-bands__log">
        <canvas ref="logCanvas" />
      </div>
      <div v-else class="mr-bands__seven">
        <div
          v-for="key in BAND_ORDER"
          :key="key"
          class="mr-bands__row"
          :data-status="statusOf(key)"
        >
          <div class="mr-bands__meta">
            <strong>{{ bandLabel(key) }}</strong>
            <span>{{ BAND_HZ_HINTS[key] }}</span>
          </div>
          <div class="mr-bands__bar-wrap">
            <i :style="{ width: barWidth(key) }" />
          </div>
          <em>{{ pct(key) }}%</em>
        </div>
      </div>
    </template>
    <div v-else class="mr-bands__blank">
      <p class="mr-bands__empty">{{ emptyText }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BAND_HZ_HINTS,
  BAND_ORDER,
  bandStatus,
  type BandKey,
  type BandMap,
  type BandMode,
  type BandStatus,
} from '../../utils/mixReviewTypes'

const props = defineProps<{
  bands?: BandMap | null
  logBands?: number[] | null
  mode?: BandMode
  /** 强制标红的频段（如命中关键 flags） */
  alertKey?: string
  emptyText?: string
}>()

const { t } = useI18n()
const logCanvas = ref<HTMLCanvasElement | null>(null)
let ro: ResizeObserver | null = null

const BAND_I18N: Record<BandKey, string> = {
  sub: 'mixReview.bandSub',
  bass: 'mixReview.bandBass',
  low_mids: 'mixReview.bandLowMids',
  mids: 'mixReview.bandMids',
  presence: 'mixReview.bandPresence',
  sibilance: 'mixReview.bandSibilance',
  air: 'mixReview.bandAir',
}

const STATUS_COLOR: Record<BandStatus, string> = {
  ok: '#1f8a5a',
  warn: '#c47b4a',
  bad: '#c0392b',
}

function bandLabel(key: BandKey) {
  return t(BAND_I18N[key])
}

const hasData = computed(() => {
  if (props.mode === 'log40') return (props.logBands?.length ?? 0) > 0
  return !!props.bands && Object.keys(props.bands).length > 0
})

function value(key: BandKey) {
  return Number(props.bands?.[key] ?? 0)
}
function pct(key: BandKey) {
  return Math.round(Math.abs(value(key)) * 100)
}
function barWidth(key: BandKey) {
  // 与右侧 % 用同一取整，避免条宽变了数字不动
  const p = pct(key)
  return p <= 0 ? '0%' : `${Math.min(100, p)}%`
}

function statusOf(key: BandKey): BandStatus {
  const forceBad = props.alertKey === key
  return bandStatus(key, value(key), forceBad)
}

function drawLog() {
  const canvas = logCanvas.value
  const data = props.logBands
  if (!canvas || !data?.length) return
  const parent = canvas.parentElement
  const cssW = parent?.clientWidth || 600
  // 可视区大约容纳 11 行，超出再滚动
  const viewH = parent?.clientHeight || 180
  const rowH = Math.max(14, viewH / 11)
  const cssH = data.length * rowH
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.floor(cssW * dpr)
  canvas.height = Math.floor(cssH * dpr)
  canvas.style.width = `${cssW}px`
  canvas.style.height = `${cssH}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, cssW, cssH)

  const mean = data.reduce((a, b) => a + b, 0) / data.length
  let variance = 0
  for (const v of data) variance += (v - mean) ** 2
  const std = Math.sqrt(variance / data.length) || 0.001
  const max = Math.max(...data, 0.001)
  const maxW = cssW - 8

  for (let i = 0; i < data.length; i += 1) {
    const v = data[i]!
    const z = Math.abs(v - mean) / std
    const status: BandStatus = z <= 1.2 ? 'ok' : z <= 2.2 ? 'warn' : 'bad'
    const w = (v / max) * maxW
    ctx.fillStyle = STATUS_COLOR[status]
    ctx.fillRect(4, i * rowH + 2, Math.max(1, w), Math.max(1, rowH - 3))
  }
}

function bindLogObserver() {
  ro?.disconnect()
  ro = null
  if (logCanvas.value?.parentElement) {
    ro = new ResizeObserver(() => drawLog())
    ro.observe(logCanvas.value.parentElement)
  }
}

onMounted(() => {
  void nextTick(() => {
    drawLog()
    bindLogObserver()
  })
})
onUnmounted(() => ro?.disconnect())
watch(
  () => [props.logBands, props.mode, hasData.value],
  async () => {
    await nextTick()
    drawLog()
    bindLogObserver()
  },
)
</script>

<style scoped lang="less">
.mr-bands {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 0.08rem;
  overflow: hidden;

  &__blank {
    position: relative;
    flex: 1;
    min-height: 1.8rem;
    background: var(--workspace-panel-muted);
    border-radius: 0.08rem;
  }

  &__empty {
    position: absolute;
    inset: 0;
    margin: 0;
    display: grid;
    place-items: center;
    font-size: 0.14rem;
    color: var(--muted-text);
  }

  &__seven {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-evenly;
    gap: 0.08rem;
    padding: 0.08rem 0.12rem;
  }

  &__row {
    display: grid;
    grid-template-columns: 1.1rem 1fr 0.5rem;
    align-items: center;
    gap: 0.12rem;
    min-height: 0.32rem;

    &[data-status='ok'] {
      i {
        background: #1f8a5a;
      }
      em {
        color: #1f8a5a;
      }
    }
    &[data-status='warn'] {
      i {
        background: #c47b4a;
      }
      em {
        color: #c47b4a;
      }
    }
    &[data-status='bad'] {
      strong,
      em {
        color: #c0392b;
      }
      i {
        background: #c0392b;
      }
    }
  }

  &__meta {
    display: flex;
    flex-direction: column;
    gap: 0.01rem;
    min-width: 0;

    strong {
      font-size: 0.13rem;
      letter-spacing: 0.03em;
      color: var(--text-color);
      line-height: 1.2;
    }
    span {
      font-size: 0.11rem;
      color: var(--muted-text);
      line-height: 1.2;
    }
  }

  &__bar-wrap {
    height: 0.2rem;
    background: color-mix(in srgb, var(--text-color) 6%, transparent);
    border-radius: 0.04rem;
    overflow: hidden;

    i {
      display: block;
      height: 100%;
      border-radius: 0.04rem;
      transition: background 0.15s ease, width 0.15s ease;
    }
  }

  em {
    font-style: normal;
    font-size: 0.13rem;
    font-weight: 600;
    text-align: right;
    color: var(--text-color);
  }

  &__log {
    flex: 1;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    background: var(--workspace-panel-muted);
    border-radius: 0.08rem;
    canvas {
      display: block;
      width: 100%;
      height: auto;
    }
  }
}
</style>
