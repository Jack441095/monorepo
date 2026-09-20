<template>
  <header class="app-header" :class="{ 'app-header--embedded': embedded }">
    <div
      class="app-header__inner"
      :class="{ 'header-container': !embedded }"
    >
      <h1 class="app-header__title">{{ t('common.title') }}</h1>
      <div class="app-header__actions">
        <button
          v-if="!embedded"
          class="app-header__icon-btn"
          type="button"
          :title="sidebarStore.collapsed ? t('sidebar.expand') : t('sidebar.collapse')"
          @click="sidebarStore.toggle()"
        >
          <svg v-if="sidebarStore.collapsed" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M15 6L9 12L15 18"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M9 6L15 12L9 18"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M5 5V19"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </svg>
        </button>
        <LanguageSelector />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSidebarStore } from '../composables/useSidebar'
import LanguageSelector from './LanguageSelector.vue'

withDefaults(
  defineProps<{
    embedded?: boolean
  }>(),
  {
    embedded: false,
  },
)

const { t } = useI18n()
const sidebarStore = useSidebarStore()
</script>

<style scoped lang="less">
.app-header {
  flex-shrink: 0;
  background: var(--floating-bg);
  z-index: 10;

  &__inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.12rem;
    min-height: var(--header-inner-min-height);
    padding-top: var(--header-padding-y);
    padding-bottom: var(--header-padding-y);
  }

  &--embedded {
    height: var(--sidebar-header-height);
    border-bottom: 1px solid var(--floating-border);

    .app-header__inner {
      height: 100%;
      min-height: 0;
      padding: 0 0.1rem 0 0.16rem;
    }

    .app-header__title {
      font-size: 0.18rem;
    }
  }

  &__title {
    margin: 0;
    font-size: var(--header-title-size);
    font-weight: var(--header-title-weight);
    line-height: 1.2;
    color: var(--header-title-color);
    letter-spacing: var(--header-title-tracking);
    text-transform: uppercase;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 0.08rem;
    flex-shrink: 0;
  }

  &__icon-btn {
    width: 0.4rem;
    height: 0.4rem;
    padding: 0;
    border: 1px solid var(--floating-border);
    border-radius: 50%;
    background: var(--floating-bg);
    color: var(--floating-icon);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;

    svg {
      width: 0.18rem;
      height: 0.18rem;
      display: block;
    }

    &:hover {
      color: var(--floating-icon-hover);
      background: var(--floating-bg-hover);
      border-color: var(--floating-border-active);
    }
  }
}
</style>
