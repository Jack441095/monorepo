<!-- 公用按钮：primary / ghost -->
<template>
  <button
    class="app-btn"
    :class="[`app-btn--${variant}`, { 'app-btn--block': block }]"
    :type="type"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'ghost'
    type?: 'button' | 'submit'
    disabled?: boolean
    block?: boolean
  }>(),
  {
    variant: 'primary',
    type: 'button',
    disabled: false,
    block: false,
  },
)
</script>

<style scoped lang="less">
.app-btn {
  min-height: 0.44rem;
  padding: 0 0.2rem;
  font-size: 0.14rem;
  font-weight: 500;
  border-radius: 0.08rem;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
  white-space: nowrap;

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  &--primary {
    color: #ffffff;
    background: #111111;
    border: none;

    &:hover:not(:disabled) {
      background: #333333;
    }
  }

  &--ghost {
    color: var(--text-color);
    background: var(--surface-bg);
    border: 1px solid var(--floating-border);

    &:hover:not(:disabled) {
      border-color: var(--floating-border-active);
      background: #f9fafb;
    }
  }

  &--block {
    width: 100%;
  }
}
</style>
