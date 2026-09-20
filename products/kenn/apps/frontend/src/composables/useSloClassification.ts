import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import {
  ApiError,
} from '../api/client'
import {
  fetchSloClassifications,
  filterSloClassifications,
  type SloClassificationItem,
  type SloClassificationResponse,
  type SloServiceStatus,
} from '../api/sloClassification'
import { fetchSloMockScenario } from '../mocks/sloClassifications'

export function readSloMockMode(): boolean {
  return String(import.meta.env.VITE_SLO_CLASSIFICATION_MOCK ?? '').trim().toLowerCase() === 'true'
}

export function useSloClassification() {
  const response = shallowRef<SloClassificationResponse | null>(null)
  const status = ref<SloServiceStatus>('loading')
  const error = ref('')
  const search = ref('')
  const category = ref('')
  const reviewOnly = ref(false)
  const selected = shallowRef<SloClassificationItem | null>(null)
  const mockMode = readSloMockMode()
  let controller: AbortController | null = null

  const categories = computed(() =>
    [...new Set((response.value?.items ?? []).map((item) => item.category).filter(Boolean))].sort(),
  )
  const filteredItems = computed(() =>
    filterSloClassifications(response.value?.items ?? [], search.value, category.value, reviewOnly.value),
  )

  async function load() {
    controller?.abort()
    controller = new AbortController()
    status.value = 'loading'
    error.value = ''
    selected.value = null
    try {
      response.value = mockMode ? await fetchSloMockScenario() : await fetchSloClassifications(controller.signal)
      status.value = response.value.items.length ? 'ready' : 'empty'
    } catch (cause) {
      response.value = null
      if (cause instanceof DOMException && cause.name === 'AbortError') return
      if (cause instanceof ApiError && cause.status === 503) status.value = 'unavailable'
      else if (cause instanceof TypeError) status.value = 'offline'
      else status.value = 'error'
      error.value = cause instanceof Error ? cause.message : 'SLO classifications could not be loaded.'
    }
  }

  onBeforeUnmount(() => controller?.abort())

  return {
    response, status, error, search, category, reviewOnly, selected, mockMode,
    categories, filteredItems, load,
  }
}
