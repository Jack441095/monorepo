<template>
  <!-- 必须单根，否则父级 v-show 无法正确隐藏 -->
  <div
    class="float-detach-root"
    :class="[
      {
        'is-fill': layout === 'fill',
        'is-stretch': layout === 'stretch',
      },
      rootClass,
    ]"
  >
    <div
      ref="rootEl"
      class="float-detach"
      :class="{
        'is-enabled': enabled,
        'is-open': open,
      }"
    >
      <!-- 原位置始终保留；通过标题栏按钮弹出 -->
      <slot
        :open-float="openFloat"
        :can-pop="Boolean(enabled && !open)"
        :show-pop="!open"
        :is-open="open"
        :floating="false"
      />
    </div>

    <Teleport :to="teleportTo">
      <div
        v-if="open"
        :key="panelKey"
        ref="panelEl"
        class="float-detach-panel"
        role="dialog"
        tabindex="-1"
        :aria-label="title"
        :style="panelStyle"
        @focusin="bringToFront"
      >
        <header class="float-detach-panel__head" @pointerdown="onPanelDragStart">
          <strong>{{ title }}</strong>
          <button
            type="button"
            class="float-detach-panel__close"
            :aria-label="t('mixReview.floatClose')"
            @pointerdown.stop
            @click="closeFloat"
          >
            ×
          </button>
        </header>
        <!-- 内容区：仅缩小后锁定默认内容尺寸并由 body 滚动；默认尺寸不出现滚动条 -->
        <div
          class="float-detach-panel__body"
          :class="{ 'is-shrunk': isShrunk }"
          @pointerdown.capture="bringToFront"
        >
          <div class="float-detach-panel__fit" :style="fitStyle">
            <slot
              :open-float="openFloat"
              :can-pop="false"
              :show-pop="false"
              :is-open="open"
              :floating="true"
            />
          </div>
        </div>
        <!-- 边缘/角点缩放：仅允许缩小到不大于打开时的默认尺寸 -->
        <span
          v-for="edge in RESIZE_EDGES"
          :key="edge"
          class="float-detach-panel__resize"
          :data-edge="edge"
          @pointerdown="onResizeStart(edge, $event)"
        />
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FLOAT_TELEPORT_HOST, nextFloatCascadeStep, nextFloatZ } from './floatDetachLayer'

const props = withDefaults(
  defineProps<{
    /** 是否允许弹出（如：仅分析完成后为 true） */
    enabled?: boolean
    /** 浮动窗标题 */
    title?: string
    /** 附加在根节点上的 class */
    rootClass?: string
    /** 受控：是否打开 */
    open?: boolean
    /**
     * fill：在纵向 flex 父级里占满剩余高度（可视化区）
     * stretch：在网格格子里 height:100%（结果卡片）
     */
    layout?: 'fill' | 'stretch' | 'inline'
  }>(),
  {
    enabled: false,
    title: '',
    rootClass: '',
    open: undefined,
    layout: 'inline',
  },
)

const emit = defineEmits<{
  'update:open': [boolean]
  opened: []
  closed: []
}>()

const { t } = useI18n()
const rootEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const innerOpen = ref(false)
const size = ref({ w: 320, h: 200 })
/** 打开时的默认尺寸：缩放上限，只可缩小不可放大 */
const maxSize = ref({ w: 320, h: 200 })
/** 默认内容区尺寸：缩小后 fit 仍按此撑开，由 body 滚动 */
const contentMin = ref({ w: 280, h: 160 })
/** 窗口左上角坐标（可多窗并存、互不抢占） */
const pos = ref({ x: 24, y: 24 })
const zIndex = ref(200)
const draggingPanel = ref(false)
const dragOrigin = { x: 0, y: 0, ox: 0, oy: 0 }
type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
const RESIZE_EDGES: ResizeEdge[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const MIN_PANEL_W = 200
const MIN_PANEL_H = 140
const resizing = ref<{
  edge: ResizeEdge
  startX: number
  startY: number
  origW: number
  origH: number
  origX: number
  origY: number
} | null>(null)

const panelKey = `float-panel-${Math.random().toString(36).slice(2, 9)}`

/** 优先挂到首页浮层宿主（与 KENN 同层），否则回退 body */
const teleportTo = ref<string | HTMLElement>('body')

function resolveTeleportHost() {
  if (typeof document === 'undefined') {
    teleportTo.value = 'body'
    return
  }
  teleportTo.value = document.querySelector(FLOAT_TELEPORT_HOST) ? FLOAT_TELEPORT_HOST : 'body'
}

const open = computed({
  get: () => (props.open === undefined ? innerOpen.value : props.open),
  set: (v: boolean) => {
    if (props.open === undefined) innerOpen.value = v
    emit('update:open', v)
  },
})

import type { CSSProperties } from 'vue'

const panelStyle = computed<CSSProperties>(() => ({
  position: (teleportTo.value === 'body' ? 'fixed' : 'absolute') as CSSProperties['position'],
  width: `${size.value.w}px`,
  height: `${size.value.h}px`,
  left: `${pos.value.x}px`,
  top: `${pos.value.y}px`,
  zIndex: zIndex.value,
}))

/** 相对打开时默认尺寸是否已缩小（任一方向） */
const isShrunk = computed(
  () => size.value.w < maxSize.value.w || size.value.h < maxSize.value.h,
)

const fitStyle = computed(() => {
  // 默认尺寸：撑满 body，不设 min，避免多出 1px 就出滚动条
  if (!isShrunk.value) {
    return {
      width: '100%',
      height: '100%',
      minWidth: '0',
      minHeight: '0',
    }
  }
  // 缩小后：内容按打开时占位撑开，由 body 滚动查看
  return {
    width: '100%',
    height: '100%',
    minWidth: `${contentMin.value.w}px`,
    minHeight: `${contentMin.value.h}px`,
  }
})

/** 标题栏 + body 内边距 + 边框；量到的原位高度需加上这笔，内容区才和原位一致 */
function panelChromeHeight() {
  const panel = panelEl.value
  if (panel) {
    const head = panel.querySelector('.float-detach-panel__head') as HTMLElement | null
    const body = panel.querySelector('.float-detach-panel__body') as HTMLElement | null
    const cs = getComputedStyle(panel)
    const bcs = body ? getComputedStyle(body) : null
    const headH = head?.offsetHeight ?? 0
    const padY = bcs
      ? (parseFloat(bcs.paddingTop) || 0) + (parseFloat(bcs.paddingBottom) || 0)
      : 0
    const borderY =
      (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0)
    return headH + padY + borderY
  }
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 100
  // head≈0.48rem（含关闭钮），body 上下 padding 0.08*2，边框约 2px
  return Math.round(0.48 * rem + 0.16 * rem + 2)
}

function panelChromeWidth() {
  const panel = panelEl.value
  if (panel) {
    const body = panel.querySelector('.float-detach-panel__body') as HTMLElement | null
    const cs = getComputedStyle(panel)
    const bcs = body ? getComputedStyle(body) : null
    const padX = bcs
      ? (parseFloat(bcs.paddingLeft) || 0) + (parseFloat(bcs.paddingRight) || 0)
      : 0
    const borderX =
      (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0)
    return padX + borderX
  }
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 100
  return Math.round(0.16 * rem + 2)
}

function syncContentMin(panelW: number, panelH: number) {
  contentMin.value = {
    w: Math.max(0, Math.round(panelW - panelChromeWidth())),
    h: Math.max(0, Math.round(panelH - panelChromeHeight())),
  }
}

function measure() {
  const el = rootEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const chrome = panelChromeHeight()
  const next = {
    w: Math.max(MIN_PANEL_W, Math.round(rect.width)),
    // 整窗高度 = 原位内容 + 浮窗装饰，避免 7 频段/感知频段底部被裁
    h: Math.max(MIN_PANEL_H, Math.round(rect.height + chrome)),
  }
  size.value = next
  // 默认尺寸即上限：之后只能缩小
  maxSize.value = { ...next }
  syncContentMin(next.w, next.h)
}

function getTeleportHostEl(): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return document.querySelector(FLOAT_TELEPORT_HOST) as HTMLElement | null
}

/** 视口坐标 → 浮层定位坐标（absolute 相对宿主 / fixed 相对视口） */
function clientToPos(clientX: number, clientY: number) {
  if (teleportTo.value === 'body') return { x: clientX, y: clientY }
  const host = getTeleportHostEl()
  if (!host) return { x: clientX, y: clientY }
  const hr = host.getBoundingClientRect()
  return { x: clientX - hr.left, y: clientY - hr.top }
}

function clampPos(x: number, y: number) {
  const pad = 8
  const host = teleportTo.value === 'body' ? null : getTeleportHostEl()
  const boundsW = host?.clientWidth ?? window.innerWidth
  const boundsH = host?.clientHeight ?? window.innerHeight
  const maxX = Math.max(pad, boundsW - size.value.w - pad)
  const maxY = Math.max(pad, boundsH - size.value.h - pad)
  return {
    x: Math.min(Math.max(pad, x), maxX),
    y: Math.min(Math.max(pad, y), maxY),
  }
}

function placeCascaded() {
  const step = nextFloatCascadeStep()
  pos.value = clampPos(24 + step, 24 + step)
}

/** 叠在当前组件所在区域：X 与原位左缘对齐，仅 Y 轻微错开 */
function placeAtSource() {
  const el = rootEl.value
  if (!el) {
    placeCascaded()
    return
  }
  const rect = el.getBoundingClientRect()
  const step = nextFloatCascadeStep()
  const p = clientToPos(rect.left, rect.top)
  pos.value = clampPos(p.x, p.y + step)
}

function placeNear(clientX: number, clientY: number) {
  // 开在指针附近，避免大窗挡死其它卡片
  const p = clientToPos(clientX + 12, clientY + 12)
  pos.value = clampPos(p.x, p.y)
}

function bringToFront() {
  // 全实例共享计数：点哪个窗，哪个就到最上层
  const z = nextFloatZ()
  zIndex.value = z
  if (panelEl.value) panelEl.value.style.zIndex = String(z)
}

/** 捕获阶段：保证点到内部 canvas/子节点时也能置顶 */
function onPanelPointerDownCapture() {
  bringToFront()
}

let detachPanelActivate: (() => void) | null = null

function bindPanelActivate() {
  detachPanelActivate?.()
  detachPanelActivate = null
  const el = panelEl.value
  if (!el) return
  el.addEventListener('pointerdown', onPanelPointerDownCapture, true)
  detachPanelActivate = () => {
    el.removeEventListener('pointerdown', onPanelPointerDownCapture, true)
    detachPanelActivate = null
  }
}

async function openFloat(anchor?: { x: number; y: number }) {
  if (!props.enabled) return
  resolveTeleportHost()
  // 已打开则置顶，不关掉其它窗
  if (open.value) {
    bringToFront()
    return
  }
  await nextTick()
  measure()
  if (anchor) placeNear(anchor.x, anchor.y)
  else placeAtSource()
  bringToFront()
  open.value = true
  emit('opened')
  // 面板挂载后再按真实标题栏高度校正，并重新贴齐原位 X
  await nextTick()
  measure()
  if (anchor) {
    placeNear(anchor.x, anchor.y)
  } else if (rootEl.value) {
    const rect = rootEl.value.getBoundingClientRect()
    const p = clientToPos(rect.left, rect.top)
    pos.value = clampPos(p.x, pos.value.y)
  } else {
    pos.value = clampPos(pos.value.x, pos.value.y)
  }
}

function closeFloat() {
  open.value = false
  emit('closed')
}

function onPanelDragStart(e: PointerEvent) {
  if (resizing.value) return
  if ((e.target as HTMLElement).closest('button')) return
  bringToFront()
  draggingPanel.value = true
  dragOrigin.x = e.clientX
  dragOrigin.y = e.clientY
  dragOrigin.ox = pos.value.x
  dragOrigin.oy = pos.value.y
}

function onPanelDragMove(e: PointerEvent) {
  if (resizing.value) return
  if (!draggingPanel.value) return
  pos.value = clampPos(
    dragOrigin.ox + (e.clientX - dragOrigin.x),
    dragOrigin.oy + (e.clientY - dragOrigin.y),
  )
}

function onPanelDragEnd() {
  draggingPanel.value = false
}

function onResizeStart(edge: ResizeEdge, e: PointerEvent) {
  if (e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  bringToFront()
  draggingPanel.value = false
  resizing.value = {
    edge,
    startX: e.clientX,
    startY: e.clientY,
    origW: size.value.w,
    origH: size.value.h,
    origX: pos.value.x,
    origY: pos.value.y,
  }
}

function onResizeMove(e: PointerEvent) {
  const r = resizing.value
  if (!r) return
  const dx = e.clientX - r.startX
  const dy = e.clientY - r.startY
  let w = r.origW
  let h = r.origH

  if (r.edge.includes('e')) w = r.origW + dx
  if (r.edge.includes('w')) w = r.origW - dx
  if (r.edge.includes('s')) h = r.origH + dy
  if (r.edge.includes('n')) h = r.origH - dy

  // 上限 = 打开时默认尺寸，下限保底可读
  w = Math.min(maxSize.value.w, Math.max(MIN_PANEL_W, Math.round(w)))
  h = Math.min(maxSize.value.h, Math.max(MIN_PANEL_H, Math.round(h)))

  // 拖左边/上边时锚住对侧，避免窗口乱跑
  let x = r.origX
  let y = r.origY
  if (r.edge.includes('w')) x = r.origX + (r.origW - w)
  if (r.edge.includes('n')) y = r.origY + (r.origH - h)

  size.value = { w, h }
  pos.value = clampPos(x, y)
}

function onResizeEnd() {
  resizing.value = null
}

watch(
  () => props.enabled,
  (ok) => {
    // 分析失效时才收起；平时只能手动关
    if (!ok && open.value) closeFloat()
  },
)

watch(open, async (isOpen) => {
  if (!isOpen) {
    detachPanelActivate?.()
    return
  }
  await nextTick()
  bindPanelActivate()
  bringToFront()
})

onMounted(() => {
  void nextTick().then(resolveTeleportHost)
  window.addEventListener('pointermove', onPanelDragMove)
  window.addEventListener('pointerup', onPanelDragEnd)
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeEnd)
  window.addEventListener('pointercancel', onResizeEnd)
  if (open.value) void nextTick().then(bindPanelActivate)
})

onUnmounted(() => {
  detachPanelActivate?.()
  window.removeEventListener('pointermove', onPanelDragMove)
  window.removeEventListener('pointerup', onPanelDragEnd)
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
  window.removeEventListener('pointercancel', onResizeEnd)
})

defineExpose({
  open: openFloat,
  close: closeFloat,
  measure,
})
</script>

<style scoped lang="less">
.float-detach-root {
  box-sizing: border-box;
  min-width: 0;
  min-height: 0;

  &.is-fill {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  &.is-stretch {
    height: 100%;
    display: flex;
    flex-direction: column;
  }
}

.float-detach {
  box-sizing: border-box;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  cursor: inherit;

  > :deep(*) {
    flex: 1 1 auto;
    min-width: 0;
    width: 100%;
    height: 100%;
  }
}
</style>

<style lang="less">
.float-detach-panel {
  /* position 由 panelStyle 按 teleport 目标切换 absolute / fixed */
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  margin: 0;
  padding:0 0.12rem 0.12rem;
  background: var(--workspace-panel);
  border: 1px solid var(--floating-border);
  border-radius: 0.1rem;
  box-shadow: var(--toast-shadow);
  overflow: hidden;
  pointer-events: auto;
  outline: none;

  &__head {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.1rem;
    padding: 0.08rem 0.08rem 0.08rem 0.12rem;
    border-bottom: 1px solid var(--floating-border);
    background: var(--workspace-panel);
    cursor: grab;
    user-select: none;
    strong {
      font-size: 0.14rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted-text);
    }
    &:active {
      cursor: grabbing;
    }
  }

  &__close {
    width: 0.32rem;
    height: 0.32rem;
    flex-shrink: 0;
    border: none;
    border-radius: 0.06rem;
    background: transparent;
    color: var(--muted-text);
    font-size: 0.22rem;
    line-height: 1;
    cursor: pointer;
    &:hover {
      background: var(--workspace-panel-muted);
      color: var(--text-color);
    }
  }

  &__body {
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    overscroll-behavior: contain;

    &.is-shrunk {
      overflow: auto;
    }
  }

  /* 锁定打开时的内容占位，缩小窗口时内容不被压扁 */
  &__fit {
    box-sizing: border-box;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;

    > * {
      flex: 1 1 auto;
      min-width: 0;
      min-height: 0;
      width: 100%;
      height: 100%;
    }
  }

  &__resize {
    position: absolute;
    z-index: 2;
    background: transparent;
    touch-action: none;
    user-select: none;

    &[data-edge='n'],
    &[data-edge='s'] {
      left: 0.1rem;
      right: 0.1rem;
      height: 0.08rem;
      cursor: ns-resize;
    }
    &[data-edge='n'] {
      top: 0;
    }
    &[data-edge='s'] {
      bottom: 0;
    }

    &[data-edge='e'],
    &[data-edge='w'] {
      top: 0.1rem;
      bottom: 0.1rem;
      width: 0.08rem;
      cursor: ew-resize;
    }
    &[data-edge='e'] {
      right: 0;
    }
    &[data-edge='w'] {
      left: 0;
    }

    &[data-edge='ne'],
    &[data-edge='nw'],
    &[data-edge='se'],
    &[data-edge='sw'] {
      width: 0.12rem;
      height: 0.12rem;
    }
    &[data-edge='ne'] {
      top: 0;
      right: 0;
      cursor: nesw-resize;
    }
    &[data-edge='nw'] {
      top: 0;
      left: 0;
      cursor: nwse-resize;
    }
    &[data-edge='se'] {
      bottom: 0;
      right: 0;
      cursor: nwse-resize;
    }
    &[data-edge='sw'] {
      bottom: 0;
      left: 0;
      cursor: nesw-resize;
    }
  }
}
</style>
