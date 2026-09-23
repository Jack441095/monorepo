<template>
  <Teleport to="body">
    <div class="app-toast-host" aria-live="polite">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="app-toast"
        :data-type="item.type"
        role="status"
      >
        {{ item.message }}
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToastState } from '../../composables/useToast'

const { toasts } = useToastState()
</script>

<style lang="less">
.app-toast-host {
  position: fixed;
  top: 0.2rem;
  left: 50%;
  z-index: 4000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.08rem;
  transform: translateX(-50%);
  pointer-events: none;
}

.app-toast {
  max-width: min(92vw, 4.8rem);
  padding: 0.1rem 0.18rem;
  border-radius: 0.08rem;
  border: 1px solid var(--toast-border);
  background: var(--toast-bg);
  color: var(--text-color);
  font-size: 0.14rem;
  line-height: 1.4;
  box-shadow: var(--toast-shadow);
  pointer-events: none;

  &[data-type='success'] {
    border-color: rgba(31, 138, 90, 0.35);
    color: #1f8a5a;
  }

  &[data-type='error'] {
    border-color: rgba(192, 57, 43, 0.35);
    color: #c0392b;
  }
}
</style>
