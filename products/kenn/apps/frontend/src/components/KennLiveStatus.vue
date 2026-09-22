<template>
  <section class="live-status" aria-label="Ableton Live status">
    <div class="live-status__connection">
      <span class="live-status__dot" :class="{ 'live-status__dot--online': project.connected }" />
      <strong>{{ project.connected ? 'Live connected' : 'Live offline' }}</strong>
      <button type="button" :disabled="refreshing" title="Refresh Live status" @click="refresh">
        {{ refreshing ? 'Checking…' : 'Refresh' }}
      </button>
    </div>
    <div class="live-status__facts">
      <span><small>Session</small>{{ project.name }}</span>
      <span><small>Tracks</small>{{ project.trackCount }}</span>
      <span><small>Last action</small>{{ lastActionLabel }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useKenn } from '../composables/useKenn'

const { project, lastActionAt, refreshSessionCard } = useKenn()
const refreshing = ref(false)

const lastActionLabel = computed(() => {
  if (!lastActionAt.value) return 'None yet'
  return lastActionAt.value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await refreshSessionCard()
  } finally {
    refreshing.value = false
  }
}

let refreshTimer: number | undefined
onMounted(() => {
  refreshTimer = window.setInterval(() => void refresh(), 10_000)
})
onBeforeUnmount(() => {
  if (refreshTimer != null) window.clearInterval(refreshTimer)
})
</script>

<style scoped lang="less">
.live-status {
  flex-shrink: 0;
  padding: 0.09rem 0.14rem 0.1rem;
  border-bottom: 1px solid var(--floating-border);
  background: color-mix(in srgb, var(--floating-bg) 88%, #0d1117);

  &__connection {
    display: flex;
    align-items: center;
    gap: 0.07rem;
    font-size: 0.12rem;

    button {
      margin-left: auto;
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--muted-text);
      font: inherit;
      font-size: 0.1rem;
      cursor: pointer;
    }
  }

  &__dot {
    width: 0.08rem;
    height: 0.08rem;
    border-radius: 50%;
    background: #ef6461;
    box-shadow: 0 0 0.08rem rgba(239, 100, 97, 0.5);

    &--online {
      background: #37d67a;
      box-shadow: 0 0 0.09rem rgba(55, 214, 122, 0.62);
    }
  }

  &__facts {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) 0.55fr 1fr;
    gap: 0.08rem;
    margin-top: 0.08rem;

    span {
      min-width: 0;
      overflow: hidden;
      color: var(--text-color);
      font-size: 0.11rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    small {
      display: block;
      margin-bottom: 0.015rem;
      color: var(--muted-text);
      font-size: 0.085rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
  }
}
</style>
