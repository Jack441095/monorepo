<template>
  <div class="home">
    <div class="home-layout">
      <!-- 须在工作区之前：FloatDetachable 挂载时就能 Teleport 到此 -->
      <div id="mix-float-root" class="home-layout__float-root" aria-hidden="true" />
      <section class="home-layout__workspace" aria-label="Audio Engineering Workspace">
        <AbletonWorkspace />
      </section>
      <aside
        class="home-layout__sidebar"
        :class="{ 'home-layout__sidebar--collapsed': sidebarStore.collapsed }"
        :style="{ zIndex: sidebarZ }"
        aria-label="KENN Sidebar"
        @pointerdown.capture="bringSidebarToFront"
      >
        <button
          v-if="!sidebarStore.collapsed"
          class="home-layout__sidebar-collapse"
          type="button"
          :title="t('sidebar.collapse')"
          :aria-label="t('sidebar.collapse')"
          @click="sidebarStore.collapse()"
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
        <div v-if="!sidebarStore.collapsed" class="home-layout__sidebar-inner">
          <AppHeader embedded class="home-layout__sidebar-header" />
          <KennChatBody class="home-layout__sidebar-body" aria-label="KENN Chat Area" />
          <KennChatInput :disabled="sending" @send="onSend" />
        </div>
        <button
          v-else
          class="home-layout__sidebar-rail"
          type="button"
          :title="t('sidebar.expand')"
          :aria-label="t('sidebar.expand')"
          @click="sidebarStore.expand()"
        >
          <span class="home-layout__sidebar-rail-label">{{ t('common.title') }}</span>
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M15 6L9 12L15 18"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { nextFloatZ } from '../../components/common/floatDetachLayer'
import { useSidebarStore } from '../../composables/useSidebar'
import { useKenn } from '../../composables/useKenn'
import AbletonWorkspace from '../../components/AbletonWorkspace.vue'
import AppHeader from '../../components/AppHeader.vue'
import KennChatBody from '../../components/KennChatBody.vue'
import KennChatInput from '../../components/KennChatInput.vue'

const { t } = useI18n()
const sidebarStore = useSidebarStore()
const { sendMessage, sending } = useKenn()
/** 与 Mix Review 浮窗共用层叠计数；点击侧栏（展开/折叠）置顶 */
const sidebarZ = ref(1)

function bringSidebarToFront() {
  sidebarZ.value = nextFloatZ()
}

const onSend = (message: string) => {
  void sendMessage(message)
}
</script>

<style scoped lang="less">
.home {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.home-layout {
  position: relative;
  flex: 1;
  display: flex;
  align-items: stretch;
  min-height: 0;
  overflow: visible;

  &__workspace {
    position: relative;
    z-index: 0;
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  &__float-root {
    position: absolute;
    inset: 0;
    /* 不设 z-index，子浮窗的 z-index 才能与侧栏直接比较 */
    pointer-events: none;
    overflow: visible;
  }

  &__sidebar {
    position: relative;
    width: 4.5rem;
    flex-shrink: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: visible;
    border-left: 1px solid var(--floating-border);
    background: var(--floating-bg);
    box-shadow: var(--sidebar-left-shadow);
    transition: width 0.25s ease;
    padding-right: 0.15rem;

    &--collapsed {
      width: var(--sidebar-rail-width);
      overflow: hidden;
    }

    &-inner {
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    &-header {
      flex-shrink: 0;
      position: sticky;
      top: 0;
      z-index: 2;
    }

    &-body {
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }
  }

  &__sidebar-collapse {
    position: absolute;
    left: 0;
    top: 50%;
    z-index: 20;
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
    transform: translate(-50%, -50%);
    box-shadow: var(--popover-shadow);
    transition: color 0.2s ease, background-color 0.2s ease, border-color 0.2s ease,
      box-shadow 0.2s ease;

    svg {
      width: 0.18rem;
      height: 0.18rem;
      display: block;
    }

    &:hover {
      color: var(--floating-icon-hover);
      background: var(--floating-bg-hover);
      border-color: var(--floating-border-active);
      box-shadow: var(--popover-shadow), 0 0 0 0.02rem rgba(255, 255, 255, 0.8);
    }
  }

  &__sidebar-rail {
    flex: 1;
    width: 100%;
    min-height: 0;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--floating-icon);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.12rem;
    transition: color 0.2s ease;

    &:hover {
      color: var(--floating-icon-hover);
    }

    svg {
      width: 0.18rem;
      height: 0.18rem;
      flex-shrink: 0;
    }
  }

  &__sidebar-rail-label {
    writing-mode: vertical-rl;
    font-size: 0.12rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    line-height: 1;
  }
}
</style>
