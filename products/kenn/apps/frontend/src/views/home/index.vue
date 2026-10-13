<template>
  <div class="home">
    <div
      class="home-layout"
      :class="{
        'home-layout--chat-left': chatSide === 'left',
        'home-layout--chat-only': !workspaceVisible,
      }"
    >
      <!-- Float root for floating windows -->
      <div id="mix-float-root" class="home-layout__float-root" aria-hidden="true" />

      <!-- Analysis Workspace (can be hidden/collapsed) -->
      <section
        v-show="workspaceVisible"
        class="home-layout__workspace"
        aria-label="Audio Engineering Workspace"
      >
        <AbletonWorkspace />
      </section>

      <!-- Floating Restore Pill Button when in Chat-Only mode -->
      <button
        v-if="!workspaceVisible"
        class="home-layout__restore-btn"
        type="button"
        title="Show Audio Analysis Workspace"
        @click="toggleWorkspaceVisible()"
      >
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.8" />
          <path d="M14 4V20" stroke="currentColor" stroke-width="1.8" />
        </svg>
        <span>Show Analysis Workspace</span>
      </button>

      <aside
        class="home-layout__sidebar"
        :class="{
          'home-layout__sidebar--collapsed': sidebarStore.collapsed && workspaceVisible,
          'home-layout__sidebar--fullscreen': !workspaceVisible,
        }"
        :style="{ zIndex: sidebarZ }"
        aria-label="KENN Sidebar"
        @pointerdown.capture="bringSidebarToFront"
      >
        <button
          v-if="!sidebarStore.collapsed && workspaceVisible"
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
        <div v-if="!sidebarStore.collapsed || !workspaceVisible" class="home-layout__sidebar-inner">
          <AppHeader embedded class="home-layout__sidebar-header" />
          <KennLiveStatus />
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
import KennLiveStatus from '../../components/KennLiveStatus.vue'

const { t } = useI18n()
const sidebarStore = useSidebarStore()
const { sendMessage, sending, chatSide, workspaceVisible, toggleWorkspaceVisible } = useKenn()
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

  &--chat-left {
    flex-direction: row-reverse;

    .home-layout__sidebar {
      border-left: none;
      border-right: 1px solid var(--floating-border);
      box-shadow: 4px 0 16px rgba(0, 0, 0, 0.4);
      padding-right: 0;
      padding-left: 0.15rem;

      .home-layout__sidebar-collapse {
        left: auto;
        right: 0;
        transform: translate(50%, -50%);

        svg {
          transform: rotate(180deg);
        }
      }
    }
  }

  &--chat-only {
    .home-layout__sidebar {
      width: 100% !important;
      border: none !important;
      padding: 0 !important;
      box-shadow: none !important;

      &-inner {
        max-width: 960px;
        margin: 0 auto;
        width: 100%;
      }
    }
  }

  &__restore-btn {
    position: absolute;
    top: 0.14rem;
    left: 0.16rem;
    z-index: 100;
    display: inline-flex;
    align-items: center;
    gap: 0.08rem;
    padding: 0.06rem 0.12rem;
    border: 1px solid var(--floating-border);
    border-radius: 0.2rem;
    background: color-mix(in srgb, var(--floating-bg) 85%, #000);
    backdrop-filter: blur(8px);
    color: var(--text-color);
    font-size: 0.12rem;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    transition: all 0.2s ease;

    svg {
      width: 0.16rem;
      height: 0.16rem;
      color: #37d67a;
    }

    &:hover {
      background: var(--floating-bg-hover);
      border-color: var(--floating-border-active);
      transform: translateY(-1px);
    }
  }

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
    width: 5.2rem;
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
