<template>
  <section class="kenn-chat-history" aria-label="AI Chat History">
    <div
      ref="listRef"
      class="kenn-chat-history__content"
      @scroll.passive="onScroll"
    >
      <article
        v-for="message in messages"
        :key="message.id"
        class="chat-message"
        :class="`chat-message--${message.role}`"
      >
        <div
          class="chat-message__avatar"
          :class="`chat-message__avatar--${message.role}`"
          aria-hidden="true"
        >
          <svg v-if="message.role === 'user'" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.8" />
            <path
              d="M6 19C6.8 15.8 9.2 14 12 14C14.8 14 17.2 15.8 18 19"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none">
            <rect x="5" y="7" width="14" height="11" rx="3" stroke="currentColor" stroke-width="1.8" />
            <circle cx="9.5" cy="12.5" r="1" fill="currentColor" />
            <circle cx="14.5" cy="12.5" r="1" fill="currentColor" />
            <path d="M9.5 15.5H14.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            <path d="M12 4V7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            <circle cx="12" cy="3" r="1" fill="currentColor" />
          </svg>
        </div>

        <div class="chat-message__bubble">
          <p v-if="message.role === 'user'" class="chat-message__text">{{ message.text }}</p>

          <template v-else>
            <p v-if="message.text" class="chat-message__text">{{ message.text }}</p>
            <ol v-if="message.steps?.length" class="chat-message__list chat-message__list--ordered">
              <li v-for="(step, index) in message.steps" :key="index">{{ step }}</li>
            </ol>
            <ul v-if="message.notes?.length" class="chat-message__list chat-message__list--bullet">
              <li v-for="(note, index) in message.notes" :key="index">
                <strong>{{ note.label }}: </strong>{{ note.text }}
              </li>
            </ul>

            <div v-if="message.findings?.length" class="chat-message__findings" aria-label="Mix advice findings">
              <article
                v-for="(finding, index) in message.findings"
                :key="`${finding.title}-${index}`"
                class="advice-finding"
                :data-severity="finding.severity"
              >
                <div class="advice-finding__header">
                  <span class="advice-finding__badge">{{ severityLabel(finding.severity) }}</span>
                  <strong>{{ finding.title }}</strong>
                  <span v-if="finding.confidence != null" class="advice-finding__confidence">
                    {{ Math.round(finding.confidence * 100) }}% confidence
                  </span>
                </div>
                <p>{{ finding.detail }}</p>
                <p v-if="finding.listeningTest" class="advice-finding__test">
                  <strong>Try this:</strong> {{ finding.listeningTest }}
                </p>
              </article>
            </div>

            <!-- DAW Action Proposal Card -->
            <KennActionCard
              v-if="'proposal' in message && message.proposal"
              :proposal="message.proposal"
              :card-status="message.actionStatus || 'pending'"
              :receipt="message.receipt"
              :error-message="message.actionError"
              @apply="applyMessageProposal(message.id)"
              @reject="rejectMessageProposal(message.id)"
              @undo="undoMessageProposal(message.id)"
            />

            <div v-if="message.sources?.length" class="chat-message__sources">
              <p class="chat-message__meta-title">{{ t('kenn.sources') }}</p>
              <ul class="chat-message__list chat-message__list--bullet">
                <li v-for="(source, index) in message.sources" :key="index">
                  {{ source.label }}
                  <span v-if="source.kind" class="chat-message__source-meta"> · {{ source.kind }}</span>
                </li>
              </ul>
            </div>
            <p v-if="message.followUp" class="chat-message__follow-up">{{ message.followUp }}</p>
            <div v-if="message.suggestions?.length" class="chat-message__suggestions">
              <p class="chat-message__meta-title">{{ t('kenn.suggestions') }}</p>
              <div class="chat-message__suggestion-row">
                <button
                  v-for="(suggestion, index) in message.suggestions"
                  :key="index"
                  type="button"
                  class="chat-message__suggestion"
                  :disabled="sending"
                  @click="onSuggestion(suggestion)"
                >
                  {{ suggestion }}
                </button>
              </div>
            </div>
          </template>
        </div>
      </article>
      <p v-if="sending" class="kenn-chat-history__typing">{{ t('kenn.thinking') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKenn } from '../composables/useKenn'
import KennActionCard from './KennActionCard.vue'

const { t } = useI18n()
const { messages, sending, sendMessage, applyMessageProposal, undoMessageProposal, rejectMessageProposal } = useKenn()

const listRef = ref<HTMLElement | null>(null)
/** 贴底跟随；用户上翻后暂停，滚回底部附近再恢复 */
let stickToBottom = true
const NEAR_BOTTOM_PX = 56

function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX
}

function onScroll() {
  const el = listRef.value
  if (!el) return
  stickToBottom = isNearBottom(el)
}

function scrollToBottom(smooth = true) {
  const el = listRef.value
  if (!el) return
  el.scrollTo({
    top: el.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  })
}

async function maybeStickBottom(force = false, smooth = true) {
  if (force) stickToBottom = true
  await nextTick()
  if (stickToBottom) scrollToBottom(smooth)
}

watch(
  () => [messages.value.length, sending.value, messages.value.at(-1)?.id] as const,
  () => {
    const last = messages.value.at(-1)
    // 自己发消息时强制贴底（常见 IM 行为）
    void maybeStickBottom(last?.role === 'user', true)
  },
)

onMounted(() => {
  void maybeStickBottom(true, false)
})

function onSuggestion(text: string) {
  void sendMessage(text)
}

function severityLabel(severity: string) {
  if (severity === 'critical') return 'High'
  if (severity === 'warning') return 'Check'
  return 'Info'
}
</script>

<style scoped lang="less">
.kenn-chat-history {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  &__content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.16rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  &__typing {
    margin: 0;
    font-size: 0.12rem;
    color: var(--muted-text);
  }
}

.chat-message {
  display: flex;
  align-items: flex-start;
  gap: var(--chat-avatar-gap);

  &--user {
    flex-direction: row-reverse;
  }

  &--assistant {
    flex-direction: row;
  }

  &__avatar {
    width: var(--chat-avatar-size);
    height: var(--chat-avatar-size);
    flex-shrink: 0;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    svg {
      width: 0.2rem;
      height: 0.2rem;
      display: block;
    }

    &--user {
      background: var(--chat-avatar-user-bg);
      color: var(--chat-avatar-user-icon);
    }

    &--assistant {
      background: #111111;
      color: #ffffff;
    }
  }

  &__bubble {
    max-width: calc(100% - var(--chat-content-offset));
    padding: 0.12rem 0.14rem;
    border-radius: 0.12rem;
    font-size: var(--chat-message-size);
    line-height: 1.55;
    color: var(--text-color);
    word-break: break-word;
  }

  &--user &__bubble {
    background: var(--bubble-user);
  }

  &--assistant &__bubble {
    background: var(--surface-bg);
    border: 1px solid var(--floating-border);
  }

  &__text {
    margin: 0;
    white-space: pre-wrap;
  }

  &__list {
    margin: 0;
    padding-left: 0.2rem;

    li + li {
      margin-top: 0.06rem;
    }

    &--ordered {
      list-style-type: decimal;
      padding-left: 0.22rem;
    }

    &--bullet {
      list-style-type: disc;
      margin-top: 0.1rem;
    }
  }

  &__follow-up {
    margin: 0.1rem 0 0;
    color: var(--muted-text);
  }

  &__meta-title {
    margin: 0.12rem 0 0.06rem;
    font-size: 0.11rem;
    color: var(--muted-text);
  }

  &__sources {
    margin-top: 0.04rem;
  }

  &__findings {
    display: grid;
    gap: 0.08rem;
    margin-top: 0.12rem;
  }

  &__source-meta {
    color: var(--muted-text);
  }

  &__suggestions {
    margin-top: 0.04rem;
  }

  &__suggestion-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.06rem;
  }

  &__suggestion {
    margin: 0;
    padding: 0.06rem 0.1rem;
    border: none;
    border-radius: 0.08rem;
    background: color-mix(in srgb, var(--text-color) 6%, transparent);
    color: var(--text-color);
    font-size: 0.12rem;
    line-height: 1.45;
    text-align: left;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--text-color) 12%, transparent);
      color: var(--floating-icon-hover);
    }

    &:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
  }
}

.advice-finding {
  --advice-accent: #55b88a;
  padding: 0.1rem 0.12rem;
  border: 1px solid color-mix(in srgb, var(--advice-accent) 55%, transparent);
  border-left: 0.035rem solid var(--advice-accent);
  border-radius: 0.08rem;
  background: color-mix(in srgb, var(--advice-accent) 8%, var(--surface-bg));
  transition: transform 0.18s ease, border-color 0.18s ease;

  &[data-severity='warning'] { --advice-accent: #e6a23c; }
  &[data-severity='critical'] { --advice-accent: #ef6461; }

  &__header {
    display: flex;
    align-items: center;
    gap: 0.07rem;
    flex-wrap: wrap;
  }

  &__badge {
    padding: 0.015rem 0.055rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--advice-accent) 20%, transparent);
    color: var(--advice-accent);
    font-size: 0.1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  &__confidence {
    margin-left: auto;
    color: var(--muted-text);
    font-size: 0.1rem;
  }

  p {
    margin: 0.07rem 0 0;
    font-size: 0.12rem;
  }

  &__test {
    color: var(--muted-text);
  }
}
</style>
