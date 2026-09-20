<!-- 语言切换 -->
<template>
  <div class="global-top-actions">
    <button
      class="lang-btn"
      :class="{ 'lang-btn--active': langModalOpen }"
      type="button"
      :title="t('language.switchLanguage')"
      @click.stop="openLanguageModal"
    >
      <svg class="lang-btn__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M3 5H13M8 3V5M6 5C6.5 8 8.2 10.8 11 13M5 14C7.5 13.2 9.6 12.1 11 10.8M14 19L17 11L20 19M15.1 16H18.9"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <div v-if="langModalOpen" class="lang-popover">
      <p class="lang-popover__title">{{ t('language.selectLanguage') }}</p>
      <div class="lang-popover__cards">
        <button
          v-for="option in languageOptions"
          :key="option.value"
          class="lang-card"
          :class="[
            `lang-card--${option.tone}`,
            { 'lang-card--active': locale === option.value },
          ]"
          type="button"
          @click="selectLanguage(option.value)"
        >
          <div class="lang-card__dot-wrap">
            <div class="lang-card__dot-ring" />
            <div class="lang-card__dot" />
          </div>
          <div class="lang-card__labels">
            <span class="lang-card__name">{{ t(`language.${option.titleKey}`) }}</span>
            <span class="lang-card__sub">{{ t(`language.${option.subtitleKey}`) }}</span>
          </div>
        </button>
      </div>
    </div>
  </div>

  <div v-if="langModalOpen" class="lang-mask" @click="closeLanguageModal" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useLocaleStore } from '../composables/useLocale'
import type { Locale } from '../utils/types'

const localeStore = useLocaleStore()
const { locale } = storeToRefs(localeStore)
const { t } = useI18n()

const langModalOpen = ref(false)

const languageOptions: Array<{
  value: Locale
  titleKey: 'mandarin' | 'english'
  subtitleKey: 'mandarinSub' | 'englishSub'
  tone: 'red' | 'green'
}> = [
  { value: 'zh-CN', titleKey: 'mandarin', subtitleKey: 'mandarinSub', tone: 'red' },
  { value: 'en-US', titleKey: 'english', subtitleKey: 'englishSub', tone: 'green' },
]

const openLanguageModal = () => {
  langModalOpen.value = !langModalOpen.value
}

const closeLanguageModal = () => {
  langModalOpen.value = false
}

const selectLanguage = (nextLocale: Locale) => {
  localeStore.setLocale(nextLocale)
  closeLanguageModal()
}
</script>

<style scoped lang="less">
.global-top-actions {
  position: relative;
  flex-shrink: 0;
  display: flex;
  gap: 0.08rem;
  direction: ltr;
}

.lang-btn {
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
  backdrop-filter: blur(10px);
  transition: all 0.2s ease;

  &__icon {
    width: 0.18rem;
    height: 0.18rem;
    display: block;
  }

  &:hover {
    color: var(--floating-icon-hover);
    background: var(--floating-bg-hover);
  }

  &--active {
    color: var(--floating-icon-hover);
    background: var(--floating-bg-active);
    border-color: var(--floating-border-active);
  }
}

.lang-popover {
  position: absolute;
  top: calc(100% + 0.08rem);
  right: 0;
  width: 2.8rem;
  padding: 0.16rem;
  background: var(--popover-bg);
  border: 1px solid var(--floating-border);
  border-radius: 0.16rem;
  box-shadow: var(--popover-shadow);
  backdrop-filter: blur(8px);
  z-index: 1250;

  &__title {
    margin: 0.04rem 0.08rem 0.2rem;
    font-size: 0.16rem;
    font-weight: 600;
    letter-spacing: 0.025rem;
    color: var(--muted-text);
  }

  &__cards {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.12rem;
  }
}

.lang-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 1.4rem;
  border: 1px solid var(--floating-border);
  border-radius: 0.12rem;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease;

  &:hover {
    transform: translateY(-0.01rem);
    border-color: var(--floating-border-active);
  }

  &--active {
    border-color: transparent;
  box-shadow:
    var(--lang-card-active-shadow),
    0 0 0 1px rgba(255, 255, 255, 0.92) inset;
  transform: translateY(-2px);
  background: var(--lang-card-active-bg);
  }

  &__dot-wrap {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 0.36rem;
    height: 0.36rem;
    margin-bottom: 0.08rem;
    border-radius: 50%;
    flex-shrink: 0;
  }

  &__dot-ring {
    position: absolute;
    inset: 0;
    border: 2px solid transparent;
    border-radius: 50%;
  }

  &__dot {
    width: 0.12rem;
    height: 0.12rem;
    border-radius: 50%;
  }

  &__labels {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    margin-top: 0.08rem;
  }

  &__name {
    font-size: 0.16rem;
    font-weight: 700;
    line-height: 1.2;
  }

  &__sub {
    margin-top: 0.04rem;
    font-size: 0.1rem;
    font-weight: 500;
    letter-spacing: 0.01rem;
    color: var(--muted-text);
  }

  &--red &__dot-wrap {
    background: var(--lang-red-bg);
  }

  &--red &__dot-ring {
    border-color: var(--lang-red-ring);
  }

  &--red &__dot {
    background: var(--lang-red-dot);
  }

  &--green &__dot-wrap {
    background: var(--lang-green-bg);
  }

  &--green &__dot-ring {
    border-color: var(--lang-green-ring);
  }

  &--green &__dot {
    background: var(--lang-green-dot);
  }
}

.lang-mask {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: transparent;
}
</style>
