<!-- 通用分页：页码切换 + 每页条数选择 -->
<template>
  <nav v-if="total > 0" class="app-pagination" aria-label="pagination">
    <div class="app-pagination__size">
      <span class="app-pagination__size-label">{{ t('pagination.pageSize') }}</span>
      <AppSelect
        :model-value="pageSize"
        :options="pageSizeSelectOptions"
        placement="top"
        @update:model-value="onPageSizeChange"
      />
    </div>

    <template v-if="totalPages > 1">
      <button
        class="app-pagination__btn"
        type="button"
        :disabled="modelValue <= 1"
        @click="go(modelValue - 1)"
      >
        {{ t('pagination.prev') }}
      </button>

      <div class="app-pagination__pages">
        <button
          v-for="page in visiblePages"
          :key="page"
          class="app-pagination__page"
          :class="{ 'app-pagination__page--active': page === modelValue }"
          type="button"
          @click="go(page)"
        >
          {{ page }}
        </button>
      </div>

      <button
        class="app-pagination__btn"
        type="button"
        :disabled="modelValue >= totalPages"
        @click="go(modelValue + 1)"
      >
        {{ t('pagination.next') }}
      </button>
    </template>

    <span class="app-pagination__info">
      {{ t('pagination.info', { page: modelValue, total: totalPages, count: total }) }}
    </span>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from './AppSelect.vue'

const props = withDefaults(
  defineProps<{
    modelValue: number
    total: number
    pageSize: number
    pageSizeOptions?: number[]
  }>(),
  {
    pageSizeOptions: () => [10, 20, 50],
  },
)

const emit = defineEmits<{
  'update:modelValue': [page: number]
  'update:pageSize': [size: number]
}>()

const { t } = useI18n()

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const pageSizeSelectOptions = computed(() =>
  props.pageSizeOptions.map((n) => ({ label: String(n), value: n })),
)

const visiblePages = computed(() => {
  const total = totalPages.value
  const current = props.modelValue
  const maxVisible = 5
  let start = Math.max(1, current - Math.floor(maxVisible / 2))
  let end = Math.min(total, start + maxVisible - 1)
  start = Math.max(1, end - maxVisible + 1)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

const go = (page: number) => {
  const next = Math.min(Math.max(1, page), totalPages.value)
  if (next !== props.modelValue) emit('update:modelValue', next)
}

const onPageSizeChange = (value: string | number) => {
  const size = Number(value)
  if (size !== props.pageSize) {
    emit('update:pageSize', size)
    emit('update:modelValue', 1)
  }
}
</script>

<style scoped lang="less">
.app-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.1rem;
  margin-top: 0.12rem;

  &__size {
    display: flex;
    align-items: center;
    gap: 0.08rem;
    margin-right: 0.04rem;
  }

  &__size-label {
    font-size: 0.12rem;
    color: var(--muted-text);
    white-space: nowrap;
  }

  &__btn {
    min-height: 0.32rem;
    padding: 0 0.12rem;
    font-size: 0.13rem;
    color: var(--text-color);
    background: var(--surface-bg);
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    cursor: pointer;
    transition: background-color 0.15s, border-color 0.15s;

    &:hover:not(:disabled) {
      border-color: var(--floating-border-active);
      background: #f9fafb;
    }

    &:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
  }

  &__pages {
    display: flex;
    gap: 0.04rem;
  }

  &__page {
    min-width: 0.32rem;
    height: 0.32rem;
    padding: 0 0.06rem;
    font-size: 0.13rem;
    color: var(--text-color);
    background: var(--surface-bg);
    border: 1px solid var(--floating-border);
    border-radius: 0.06rem;
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      border-color: var(--floating-border-active);
    }

    &--active {
      color: #ffffff;
      background: #111111;
      border-color: #111111;
      font-weight: 600;
    }
  }

  &__info {
    margin-left: auto;
    font-size: 0.12rem;
    color: var(--muted-text);
  }
}
</style>
