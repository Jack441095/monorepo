<template>
  <div class="mr-wave">
    <canvas v-show="hasPeaks" ref="canvasEl" class="mr-wave__canvas" />
    <p v-if="!hasPeaks" class="mr-wave__empty">{{ emptyText }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  peaks?: Float32Array | null
  emptyText?: string
}>()
const canvasEl = ref<HTMLCanvasElement | null>(null)
let ro: ResizeObserver | null = null

const hasPeaks = computed(() => (props.peaks?.length ?? 0) > 0)

/** 将峰值重采样为每 CSS 像素一列（桶内取最大） */
function resamplePeaks(peaks: Float32Array, cols: number): Float32Array {
  const out = new Float32Array(cols)
  const n = peaks.length
  if (!n || cols <= 0) return out
  for (let x = 0; x < cols; x += 1) {
    const start = Math.floor((x / cols) * n)
    const end = Math.max(start + 1, Math.floor(((x + 1) / cols) * n))
    let max = 0
    let sum = 0
    let count = 0
    for (let i = start; i < end && i < n; i += 1) {
      const v = peaks[i] ?? 0
      if (v > max) max = v
      sum += v
      count += 1
    }
    const rmsApprox = count ? sum / count : 0
    out[x] = max * 0.72 + rmsApprox * 0.28
  }
  return out
}

function drawWaveform(ctx: CanvasRenderingContext2D, peaks: Float32Array, w: number, h: number) {
  const cols = Math.max(1, Math.floor(w))
  const samples = resamplePeaks(peaks, cols)
  let max = 0.001
  for (let i = 0; i < samples.length; i += 1) max = Math.max(max, samples[i] ?? 0)

  const mid = h / 2
  const amp = h * 0.48

  // 只画实心填充轮廓，不描边、不逐像素竖条
  ctx.beginPath()
  ctx.moveTo(0, mid)
  for (let x = 0; x < cols; x += 1) {
    const half = Math.max(0.5, ((samples[x] ?? 0) / max) * amp)
    ctx.lineTo(x, mid - half)
  }
  for (let x = cols - 1; x >= 0; x -= 1) {
    const half = Math.max(0.5, ((samples[x] ?? 0) / max) * amp)
    ctx.lineTo(x, mid + half)
  }
  ctx.closePath()
  ctx.fillStyle = 'rgba(34, 160, 90, 0.85)'
  ctx.fill()
}

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const parent = canvas.parentElement
  const cssW = Math.max(1, parent?.clientWidth || 600)
  // canvas 高度为 mr-wave 的一半，外层盒子高度不变
  const cssH = Math.max(1, Math.floor((parent?.clientHeight || 200) * 0.5))
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.floor(cssW * dpr)
  canvas.height = Math.floor(cssH * dpr)
  canvas.style.width = `${cssW}px`
  canvas.style.height = `${cssH}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.fillStyle = '#f3f5f8'
  ctx.fillRect(0, 0, cssW, cssH)
  if (!props.peaks?.length) return
  drawWaveform(ctx, props.peaks, cssW, cssH)
}

onMounted(() => {
  draw()
  if (canvasEl.value?.parentElement) {
    ro = new ResizeObserver(() => draw())
    ro.observe(canvasEl.value.parentElement)
  }
})
onUnmounted(() => ro?.disconnect())
watch(() => props.peaks, () => draw())
</script>

<style scoped lang="less">
.mr-wave {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  min-height: 1.8rem;
  box-sizing: border-box;
  background: #f3f5f8;
  border-radius: 0.08rem;
  overflow: hidden;

  &__canvas {
    display: block;
    width: 100%;
    height: 50%;
    flex: 0 0 auto;
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
}
</style>
