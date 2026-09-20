<template>
  <section class="kenn-project-info" aria-label="Current Project Info">
    <button
      class="kenn-project-info__toggle"
      type="button"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="kenn-project-info__title">{{ t('kenn.projectInfo') }}</span>
      <svg
        class="kenn-project-info__chevron"
        :class="{ 'kenn-project-info__chevron--expanded': expanded }"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M6 9L12 15L18 9"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <div v-show="expanded" class="kenn-project-info__content">
      <p v-if="!useMock && project.sessionStatus === 'dispatched'" class="kenn-project-info__hint">
        {{ t('kenn.sessionDispatched') }}
      </p>
      <p v-else-if="!useMock && !project.connected" class="kenn-project-info__hint">
        {{ t('kenn.sessionDisconnected') }}
      </p>
      <p v-else-if="useMock" class="kenn-project-info__hint">{{ t('kenn.mockProjectHint') }}</p>

      <dl class="kenn-project-info__meta">
        <div v-for="item in metaFields" :key="item.key" class="kenn-project-info__row">
          <dt>{{ t(item.labelKey) }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>

      <div class="kenn-project-info__section">
        <p class="kenn-project-info__section-title">{{ t('kenn.activeEffects') }}</p>
        <div v-if="project.effects.length" class="kenn-project-info__tags">
          <span v-for="effect in project.effects" :key="effect" class="kenn-project-info__tag">
            {{ effect }}
          </span>
        </div>
        <p v-else class="kenn-project-info__hint">{{ t('kenn.emptyEffects') }}</p>
      </div>

      <div class="kenn-project-info__section">
        <p class="kenn-project-info__section-title">{{ t('kenn.references') }}</p>
        <ul v-if="project.references.length" class="kenn-project-info__list">
          <li v-for="reference in project.references" :key="reference">{{ reference }}</li>
        </ul>
        <p v-else class="kenn-project-info__hint">{{ t('kenn.emptyReferences') }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKenn, refreshSessionCard } from '../composables/useKenn'

const { t } = useI18n()
const expanded = ref(true)
const { project, useMock } = useKenn()

onMounted(() => {
  void refreshSessionCard()
})

const metaFields = computed(() => [
  { key: 'name', labelKey: 'kenn.projectName', value: project.value.name },
  { key: 'daw', labelKey: 'kenn.daw', value: project.value.daw },
  { key: 'bpm', labelKey: 'kenn.bpm', value: project.value.bpm },
  { key: 'key', labelKey: 'kenn.key', value: project.value.key },
  { key: 'focusTrack', labelKey: 'kenn.focusTrack', value: project.value.focusTrack },
])
</script>

<style scoped lang="less">
.kenn-project-info {
  flex-shrink: 0;
  border-top: 1px solid var(--floating-border);
  background: var(--floating-bg);

  &__toggle {
    width: 100%;
    padding: 0.12rem 0.16rem;
    border: none;
    background: transparent;
    color: var(--text-color);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.08rem;
    transition: color 0.2s ease;

    &:hover {
      color: var(--floating-icon-hover);
    }
  }

  &__title {
    font-size: 0.14rem;
    font-weight: 600;
    line-height: 1.2;
  }

  &__chevron {
    width: 0.16rem;
    height: 0.16rem;
    flex-shrink: 0;
    color: var(--muted-text);
    transition: transform 0.2s ease;

    &--expanded {
      transform: rotate(180deg);
    }
  }

  &__content {
    max-height: var(--kenn-project-info-max-height);
    overflow-y: auto;
    padding: 0 0.16rem 0.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.08rem;
  }

  &__hint {
    margin: 0;
    font-size: 0.11rem;
    line-height: 1.35;
    color: var(--muted-text);
  }

  &__meta {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
  }

  &__row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.12rem;
    font-size: 0.11rem;
    line-height: 1.35;

    dt {
      flex-shrink: 0;
      margin: 0;
      color: var(--muted-text);
    }

    dd {
      margin: 0;
      text-align: right;
      color: var(--text-color);
      word-break: break-word;
    }
  }

  &__section {
    display: flex;
    flex-direction: column;
    gap: 0.04rem;
  }

  &__section-title {
    margin: 0;
    font-size: 0.11rem;
    font-weight: 600;
    color: var(--muted-text);
  }

  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.06rem;
  }

  &__tag {
    padding: 0.04rem 0.08rem;
    border-radius: 0.06rem;
    background: var(--file-card-bg);
    font-size: 0.11rem;
    line-height: 1.3;
    color: var(--text-color);
  }

  &__list {
    margin: 0;
    padding-left: 0.16rem;
    font-size: 0.11rem;
    line-height: 1.35;
    color: var(--text-color);

    li + li {
      margin-top: 0.02rem;
    }
  }
}
</style>
