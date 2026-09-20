<template>
  <div class="kenn-chat-input-wrapper">
    <div class="kenn-quick-prompts">
      <button
        type="button"
        class="kenn-quick-chip"
        :disabled="disabled"
        @click="emit('send', 'add EQ 8 to channel 4')"
      >
        <span class="kenn-chip-icon">⚡</span> add EQ 8 to channel 4
      </button>
      <button
        type="button"
        class="kenn-quick-chip"
        :disabled="disabled"
        @click="emit('send', 'What curve works best for 808s?')"
      >
        <span class="kenn-chip-icon">🎛️</span> 808 Curve
      </button>
      <button
        type="button"
        class="kenn-quick-chip"
        :disabled="disabled"
        @click="emit('send', 'Check mix headroom and master bus')"
      >
        <span class="kenn-chip-icon">📊</span> Mix Headroom
      </button>
    </div>
    <div class="kenn-chat-input">
      <input
        v-model="message"
        class="kenn-chat-input__field"
        type="text"
        :placeholder="t('chat.placeholder')"
        @keydown.enter="onSend"
      />
      <button
        class="kenn-chat-input__send"
        type="button"
        :title="t('chat.send')"
        :disabled="!message.trim() || disabled"
        @click="onSend"
      >
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M5 12H19M19 12L13 6M19 12L13 18"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
  }>(),
  { disabled: false },
)

const emit = defineEmits<{
  send: [message: string]
}>()

const { t } = useI18n()
const message = ref('')

const onSend = () => {
  const text = message.value.trim()
  if (!text || props.disabled) return
  emit('send', text)
  message.value = ''
}
</script>

<style scoped lang="less">
.kenn-chat-input-wrapper {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--floating-bg);
}

.kenn-quick-prompts {
  display: flex;
  align-items: center;
  gap: 0.08rem;
  padding: 0.08rem 0.16rem 0.04rem;
  overflow-x: auto;
  scrollbar-width: none;
  &::-webkit-scrollbar {
    display: none;
  }
}

.kenn-quick-chip {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.04rem;
  padding: 0.05rem 0.1rem;
  font-size: 0.11rem;
  font-weight: 600;
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 0.14rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    background: rgba(59, 130, 246, 0.18);
    border-color: rgba(59, 130, 246, 0.5);
    transform: translateY(-1px);
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .kenn-chip-icon {
    font-size: 0.11rem;
  }
}

.kenn-chat-input {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.1rem;
  padding: 0.12rem 0.16rem;
  // border-top: 1px solid var(--floating-border);
  padding: 0.08rem 0.16rem 0.12rem;
  background: var(--floating-bg);

  &__field {
    flex: 1;
    min-width: 0;
    height: 0.45rem;
    padding: 0 0.14rem;
    border: 1px solid var(--input-border);
    border-radius: 0.2rem;
    background: var(--input-bg);
    color: var(--input-text);
    box-shadow: var(--input-shadow);
    font-size: 0.14rem;
    outline: none;
    transition: border-color 0.2s ease;

    &::placeholder {
      color: var(--input-placeholder);
    }

    &:focus {
      border-color: var(--floating-border-active);
    }
  }

  &__send {
    width: 0.4rem;
    height: 0.4rem;
    flex-shrink: 0;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: var(--send-btn-bg);
    color: var(--send-icon-color);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.2s ease;

    svg {
      width: 0.18rem;
      height: 0.18rem;
      display: block;
    }

    &:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }

    &:hover:not(:disabled) {
      opacity: 0.88;
    }
  }
}
</style>
