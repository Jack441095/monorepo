<template>
  <div class="kenn-chat-body">
    <KennChatHistory />
    <KennProjectInfo />
  </div>
</template>

<script setup lang="ts">
import KennChatHistory from './KennChatHistory.vue'
import KennProjectInfo from './KennProjectInfo.vue'
</script>

<style scoped lang="less">
.kenn-chat-body {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
