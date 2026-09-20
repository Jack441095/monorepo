<template>
  <div class="app-shell">
    <main class="app-main">
      <router-view />
    </main>
    <AppToast />
  </div>
</template>

<script setup lang="ts">
import AppToast from './components/common/AppToast.vue'
</script>

<style scoped lang="less">
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 0;
  background: var(--surface-bg);
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
