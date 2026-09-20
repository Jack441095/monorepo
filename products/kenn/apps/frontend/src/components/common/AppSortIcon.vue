<!-- 表格列排序图标：双箭头，激活方向高亮 -->
<template>
  <svg
    class="app-sort-icon"
    width="12"
    height="12"
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      class="app-sort-icon__arrow app-sort-icon__arrow--up"
      :class="{ 'app-sort-icon__arrow--active': active && order === 'asc' }"
      d="M24 6L15 19H33L24 6Z"
      fill="none"
      stroke-width="4"
      stroke-linejoin="round"
    />
    <path
      class="app-sort-icon__arrow app-sort-icon__arrow--down"
      :class="{ 'app-sort-icon__arrow--active': active && order === 'desc' }"
      d="M24 42L15 29H33L24 42Z"
      fill="none"
      stroke-width="4"
      stroke-linejoin="round"
    />
  </svg>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    active?: boolean
    order?: 'asc' | 'desc'
  }>(),
  {
    active: false,
    order: 'desc',
  },
)
</script>

<style scoped lang="less">
.app-sort-icon {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;

  &__arrow {
    stroke: var(--sort-icon-muted, #9b9b9b);
    transition: stroke 0.15s;

    &--active {
      stroke: var(--sort-icon-active, var(--text-color));
    }
  }
}
</style>
