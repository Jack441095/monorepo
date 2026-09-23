<!-- 美化下拉选择：支持 auto/top/bottom/left/right，列表 Teleport 避免被裁剪 -->
<template>
  <div
    ref="rootRef"
    class="app-select"
    :class="{ 'app-select--open': open, 'app-select--disabled': disabled }"
  >
    <button
      ref="triggerRef"
      :id="id"
      class="app-select__trigger"
      type="button"
      :disabled="disabled"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click.stop="toggle"
    >
      <span class="app-select__value">{{ selectedLabel }}</span>
      <svg class="app-select__arrow" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
      </svg>
    </button>

    <Teleport to="body">
      <Transition :name="transitionName">
        <ul
          v-if="open"
          ref="dropdownRef"
          class="app-select__dropdown"
          :class="`app-select__dropdown--${resolvedPlacement}`"
          :style="dropdownStyle"
          role="listbox"
        >
          <li
            v-for="opt in options"
            :key="String(opt.value)"
            class="app-select__option"
            :class="{ 'app-select__option--active': opt.value === modelValue }"
            role="option"
            :aria-selected="opt.value === modelValue"
            @click.stop="select(opt.value)"
          >
            {{ opt.label }}
          </li>
        </ul>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface SelectOption {
  label: string
  value: string | number
}

/** 弹层方向：auto 按视口自动选，也可指定 top / bottom / left / right */
export type SelectPlacement = 'auto' | 'bottom' | 'top' | 'left' | 'right'

const GAP = 6
const OPTION_HEIGHT = 36
const DROPDOWN_PADDING = 8

const props = withDefaults(
  defineProps<{
    modelValue: string | number
    options: SelectOption[]
    id?: string
    disabled?: boolean
    placement?: SelectPlacement
  }>(),
  {
    disabled: false,
    placement: 'auto',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const resolvedPlacement = ref<Exclude<SelectPlacement, 'auto'>>('bottom')
const dropdownStyle = ref<Record<string, string>>({})

const selectedLabel = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label ?? String(props.modelValue),
)

const transitionName = computed(() => {
  if (resolvedPlacement.value === 'top') return 'app-select-drop-top'
  if (resolvedPlacement.value === 'left') return 'app-select-drop-left'
  if (resolvedPlacement.value === 'right') return 'app-select-drop-right'
  return 'app-select-drop-bottom'
})

const estimateDropdownHeight = () =>
  props.options.length * OPTION_HEIGHT + DROPDOWN_PADDING

const pickAutoPlacement = (rect: DOMRect, dropdownHeight: number, dropdownWidth: number) => {
  const spaceBelow = window.innerHeight - rect.bottom - GAP
  const spaceAbove = rect.top - GAP
  const spaceRight = window.innerWidth - rect.right - GAP
  const spaceLeft = rect.left - GAP

  const fits = {
    bottom: spaceBelow >= dropdownHeight,
    top: spaceAbove >= dropdownHeight,
    right: spaceRight >= dropdownWidth,
    left: spaceLeft >= dropdownWidth,
  }

  if (fits.bottom) return 'bottom'
  if (fits.top) return 'top'
  if (fits.right) return 'right'
  if (fits.left) return 'left'

  const ranked = [
    { dir: 'bottom' as const, space: spaceBelow },
    { dir: 'top' as const, space: spaceAbove },
    { dir: 'right' as const, space: spaceRight },
    { dir: 'left' as const, space: spaceLeft },
  ].sort((a, b) => b.space - a.space)

  return ranked[0].dir
}

const updatePosition = () => {
  const trigger = triggerRef.value
  if (!trigger || !open.value) return

  const rect = trigger.getBoundingClientRect()
  const dropdownHeight = dropdownRef.value?.offsetHeight || estimateDropdownHeight()
  const dropdownWidth = dropdownRef.value?.offsetWidth || Math.max(rect.width, 120)

  let placement = props.placement
  if (placement === 'auto') {
    placement = pickAutoPlacement(rect, dropdownHeight, dropdownWidth)
  }

  resolvedPlacement.value = placement

  const style: Record<string, string> = {
    position: 'fixed',
    zIndex: '1300',
    minWidth: `${rect.width}px`,
  }

  switch (placement) {
    case 'top':
      style.left = `${rect.left}px`
      style.bottom = `${window.innerHeight - rect.top + GAP}px`
      style.maxHeight = `${Math.max(120, rect.top - GAP - 8)}px`
      break
    case 'bottom':
      style.left = `${rect.left}px`
      style.top = `${rect.bottom + GAP}px`
      style.maxHeight = `${Math.max(120, window.innerHeight - rect.bottom - GAP - 8)}px`
      break
    case 'left':
      style.top = `${rect.top}px`
      style.right = `${window.innerWidth - rect.left + GAP}px`
      style.maxWidth = `${Math.max(120, rect.left - GAP - 8)}px`
      break
    case 'right':
      style.top = `${rect.top}px`
      style.left = `${rect.right + GAP}px`
      style.maxWidth = `${Math.max(120, window.innerWidth - rect.right - GAP - 8)}px`
      break
  }

  dropdownStyle.value = style
}

const bindPositionListeners = () => {
  window.addEventListener('scroll', updatePosition, true)
  window.addEventListener('resize', updatePosition)
}

const unbindPositionListeners = () => {
  window.removeEventListener('scroll', updatePosition, true)
  window.removeEventListener('resize', updatePosition)
}

const toggle = async () => {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    await nextTick()
    updatePosition()
    await nextTick()
    updatePosition()
    bindPositionListeners()
  } else {
    unbindPositionListeners()
  }
}

const select = (value: string | number) => {
  emit('update:modelValue', value)
  open.value = false
  unbindPositionListeners()
}

const onClickOutside = (event: MouseEvent) => {
  const target = event.target as Node
  if (rootRef.value?.contains(target) || dropdownRef.value?.contains(target)) return
  if (open.value) {
    open.value = false
    unbindPositionListeners()
  }
}

watch(
  () => props.options.length,
  () => {
    if (open.value) nextTick(updatePosition)
  },
)

onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
  unbindPositionListeners()
})
</script>

<style scoped lang="less">
.app-select {
  position: relative;
  display: inline-block;

  &--open &__trigger {
    border-color: var(--floating-border-active);
  }

  &--open &__arrow {
    transform: rotate(180deg);
  }

  &--disabled {
    opacity: 0.55;
    pointer-events: none;
  }

  &__trigger {
    display: inline-flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.12rem;
    min-width: 1.2rem;
    height: 0.44rem;
    padding: 0 0.12rem 0 0.14rem;
    font-size: 0.14rem;
    color: var(--text-color);
    background: var(--surface-bg);
    border: 1px solid var(--floating-border);
    border-radius: 0.08rem;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s;

    &:hover:not(:disabled) {
      border-color: var(--floating-border-active);
    }

    &:focus-visible {
      outline: none;
      border-color: var(--floating-border-active);
      box-shadow: 0 0 0 0.02rem rgba(15, 23, 42, 0.06);
    }
  }

  &__value {
    line-height: 1;
  }

  &__arrow {
    width: 0.12rem;
    height: 0.12rem;
    color: var(--muted-text);
    transition: transform 0.2s;
    flex-shrink: 0;
  }
}

.app-select__dropdown {
  margin: 0;
  padding: 0.04rem;
  list-style: none;
  background: var(--popover-bg);
  border: 1px solid var(--floating-border);
  border-radius: 0.08rem;
  box-shadow: var(--popover-shadow);
  backdrop-filter: blur(8px);
  overflow-y: auto;
}

.app-select__option {
  padding: 0.08rem 0.12rem;
  font-size: 0.14rem;
  color: var(--text-color);
  border-radius: 0.06rem;
  cursor: pointer;
  transition: background-color 0.15s;

  &:hover {
    background: var(--workspace-panel-muted);
  }

  &--active {
    background: var(--workspace-panel-muted);
    font-weight: 600;
  }
}

.app-select-drop-bottom-enter-active,
.app-select-drop-bottom-leave-active,
.app-select-drop-top-enter-active,
.app-select-drop-top-leave-active,
.app-select-drop-left-enter-active,
.app-select-drop-left-leave-active,
.app-select-drop-right-enter-active,
.app-select-drop-right-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.app-select-drop-bottom-enter-from,
.app-select-drop-bottom-leave-to {
  opacity: 0;
  transform: translateY(-0.04rem);
}

.app-select-drop-top-enter-from,
.app-select-drop-top-leave-to {
  opacity: 0;
  transform: translateY(0.04rem);
}

.app-select-drop-left-enter-from,
.app-select-drop-left-leave-to {
  opacity: 0;
  transform: translateX(0.04rem);
}

.app-select-drop-right-enter-from,
.app-select-drop-right-leave-to {
  opacity: 0;
  transform: translateX(-0.04rem);
}
</style>
