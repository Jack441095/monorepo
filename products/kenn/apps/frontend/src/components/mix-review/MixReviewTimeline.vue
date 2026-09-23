<template>
  <div class="mr-tl">
    <div class="mr-tl__plot">
      <canvas ref="mainEl" />
      <p v-if="!hasData" class="mr-tl__empty">{{ emptyText }}</p>
    </div>
    <div v-if="hasScope" class="mr-tl__scope">
      <div class="mr-tl__scope-card">
        <canvas ref="scopeEl" />
        <span class="mr-tl__scope-label">{{ t('mixReview.vectorscope') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { CorrelationTimeline } from '../../utils/mixReviewTypes'

const props = defineProps<{ timeline?: CorrelationTimeline | null; emptyText?: string }>()
const { t } = useI18n()
const mainEl = ref<HTMLCanvasElement | null>(null)
const scopeEl = ref<HTMLCanvasElement | null>(null)
let ro: ResizeObserver | null = null

const hasData = computed(() => (props.timeline?.correlation?.length ?? 0) > 1)
const hasScope = computed(() => (props.timeline?.vectorscope_points?.length ?? 0) > 2)

/** 绘制轨道线：序列均值落在 centerY */
function drawTrack(
  ctx: CanvasRenderingContext2D,
  values: number[],
  w: number,
  centerY: number,
  amp: number,
  color: string,
) {
  if (values.length < 2) return
  let min = Infinity
  let max = -Infinity
  let sum = 0
  for (const v of values) {
    const n = Number(v)
    if (!Number.isFinite(n)) continue
    min = Math.min(min, n)
    max = Math.max(max, n)
    sum += n
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return
  const mean = sum / values.length
  const span = Math.max(Math.abs(max - mean), Math.abs(min - mean), 0.05)

  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'
  ctx.beginPath()
  for (let i = 0; i < values.length; i += 1) {
    const x = (i / (values.length - 1)) * w
    const y = centerY - ((Number(values[i]) - mean) / span) * amp
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
}

function redraw() {
  const canvas = mainEl.value
  if (canvas) {
    const parent = canvas.parentElement
    const cssW = Math.max(1, parent?.clientWidth || 500)
    // 外层 plot 高度不变；波浪 canvas 减半并居中
    const cssH = Math.max(1, Math.floor((parent?.clientHeight || 180) * 0.5))
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = Math.floor(cssW * dpr)
    canvas.height = Math.floor(cssH * dpr)
    canvas.style.width = `${cssW}px`
    canvas.style.height = `${cssH}px`
    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, cssW, cssH)
      // 上下两条轨道，各自在半区内垂直居中（无中间灰线）
      const amp = cssH * 0.16
      drawTrack(ctx, props.timeline?.correlation || [], cssW, cssH * 0.34, amp, '#111111')
      drawTrack(ctx, props.timeline?.balance || [], cssW, cssH * 0.66, amp, '#c47b4a')
    }
  }
  drawVectorscope(props.timeline?.vectorscope_points)
}

function drawVectorscope(points?: Array<[number, number]> | null) {
  const scope = scopeEl.value
  if (!scope || !points?.length) return

  const parent = scope.parentElement
  // 绘制区域保持正方形
  const box = Math.max(
    1,
    Math.floor(Math.min(parent?.clientWidth || 160, parent?.clientHeight || 160)),
  )
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  scope.width = Math.floor(box * dpr)
  scope.height = Math.floor(box * dpr)
  scope.style.width = `${box}px`
  scope.style.height = `${box}px`
  const size = box
  const ctx = scope.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const cx = size / 2
  // 圆心略上移，给底部文案留空
  const cy = size * 0.46
  const radius = size * 0.38

  ctx.fillStyle = '#F4F6F8'
  ctx.fillRect(0, 0, size, size)

  // 外圈 + 十字线
  ctx.strokeStyle = 'rgba(17, 17, 17, 0.22)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(cx - radius, cy)
  ctx.lineTo(cx + radius, cy)
  ctx.moveTo(cx, cy - radius)
  ctx.lineTo(cx, cy + radius)
  ctx.stroke()

  // 自动放大，让点云铺满圆（接口数值很小时也能看清）
  let maxAbs = 0.001
  for (const pt of points) {
    maxAbs = Math.max(maxAbs, Math.abs(pt[0] ?? 0), Math.abs(pt[1] ?? 0))
  }
  const scale = (radius * 0.92) / maxAbs
  const dot = Math.max(2.2, size * 0.018)

  for (const pt of points) {
    const x = cx + (pt[0] ?? 0) * scale
    const y = cy - (pt[1] ?? 0) * scale
    const dx = x - cx
    const dy = y - cy
    if (dx * dx + dy * dy > radius * radius) continue
    const g = ctx.createRadialGradient(x, y, 0, x, y, dot * 1.6)
    g.addColorStop(0, 'rgba(34, 160, 90, 0.95)')
    g.addColorStop(1, 'rgba(34, 160, 90, 0.15)')
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(x, y, dot, 0, Math.PI * 2)
    ctx.fill()
  }
}

onMounted(() => {
  redraw()
  const root = mainEl.value?.closest('.mr-tl')
  if (root) {
    ro = new ResizeObserver(() => redraw())
    ro.observe(root)
  }
})
onUnmounted(() => ro?.disconnect())
watch(() => props.timeline, () => redraw(), { deep: true })
</script>

<style scoped lang="less">
.mr-tl {
  display: flex;
  gap: 0.14rem;
  height: 100%;
  min-height: 1.8rem;
  &__plot {
    position: relative;
    display: flex;
    align-items: center;
    flex: 1;
    min-width: 0;
    background: var(--workspace-panel-muted);
    border-radius: 0.08rem;
    overflow: hidden;
    canvas {
      display: block;
      width: 100%;
      height: 50%;
      flex: 0 0 auto;
    }
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
  &__scope {
    align-self: stretch;
    height: 100%;
    aspect-ratio: 1 / 1;
    width: auto;
    flex: 0 0 auto;
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  &__scope-card {
    position: relative;
    width: 100%;
    height: 100%;
    aspect-ratio: 1 / 1;
    background: var(--workspace-panel-muted);
    border: 1px solid var(--floating-border);
    border-radius: 0.08rem;
    overflow: hidden;
    canvas {
      display: block;
      width: 100%;
      height: 100%;
    }
  }

  &__scope-label {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1;
    padding: 0.06rem 0.04rem;
    text-align: center;
    font-size: 0.12rem;
    color: var(--muted-text);
    background: var(--workspace-panel-muted);
  }
}
</style>
