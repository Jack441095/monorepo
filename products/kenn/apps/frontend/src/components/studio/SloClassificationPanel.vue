<template>
  <section class="slo-panel" aria-labelledby="slo-title">
    <header class="slo-panel__header">
      <div>
        <div class="slo-panel__eyebrow">SLO · SAMPLE LIBRARY</div>
        <h2 id="slo-title">Classification review</h2>
        <p>Read-only classifications from SLO. Labels marked for review have not been forced into a known class.</p>
      </div>
      <div class="slo-panel__header-actions">
        <span v-if="mockMode" class="slo-panel__mock" role="status">Mock data</span>
        <button type="button" class="slo-panel__retry" :disabled="status === 'loading'" @click="load">
          {{ status === 'loading' ? 'Loading…' : 'Refresh' }}
        </button>
      </div>
    </header>

    <div v-if="response" class="slo-panel__summary" aria-label="Classification summary">
      <div><strong>{{ response.summary.total }}</strong><span>Classifications</span></div>
      <div><strong>{{ response.summary.needsReview }}</strong><span>Need review</span></div>
      <div><strong>{{ response.summary.stale }}</strong><span>Stale</span></div>
      <div><strong>{{ filteredItems.length }}</strong><span>Shown</span></div>
    </div>

    <div v-if="response" class="slo-panel__filters" role="search">
      <label>
        <span>Search samples</span>
        <input v-model="search" type="search" placeholder="Name, label or tag" />
      </label>
      <label>
        <span>Category</span>
        <select v-model="category">
          <option value="">All categories</option>
          <option v-for="option in categories" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <label class="slo-panel__check">
        <input v-model="reviewOnly" type="checkbox" />
        <span>Needs review only</span>
      </label>
    </div>

    <div v-if="status === 'loading'" class="slo-panel__state" role="status">
      <span class="slo-panel__spinner" aria-hidden="true" />
      Loading SLO classifications…
    </div>
    <div v-else-if="status !== 'ready' && status !== 'empty'" class="slo-panel__state slo-panel__state--error" role="alert">
      <strong>{{ status === 'offline' ? 'KENN is offline' : status === 'unavailable' ? 'SLO is unavailable' : 'Could not load classifications' }}</strong>
      <span>{{ error }}</span>
      <button type="button" @click="load">Try again</button>
    </div>
    <div v-else-if="status === 'empty'" class="slo-panel__state">
      <strong>No classifications yet</strong>
      <span>Scan a sample library in SLO, then refresh this view.</span>
    </div>
    <div v-else-if="filteredItems.length === 0" class="slo-panel__state">
      <strong>No matching samples</strong>
      <span>Clear a filter or broaden the search.</span>
    </div>

    <div v-else class="slo-panel__content">
      <ul class="slo-panel__list" aria-label="Classified samples">
        <li v-for="item in filteredItems" :key="item.id">
          <button
            type="button"
            :class="{ 'is-selected': selected?.id === item.id }"
            :aria-pressed="selected?.id === item.id"
            @click="selected = item"
          >
            <span class="slo-panel__item-main">
              <strong>{{ item.displayName }}</strong>
              <span>{{ item.category || 'Uncategorised' }}<template v-if="item.subcategory"> · {{ item.subcategory }}</template></span>
            </span>
            <span class="slo-panel__item-status" :data-review="item.reviewRequired">
              {{ item.reviewRequired ? 'Review' : item.primaryLabel }}
            </span>
            <span class="slo-panel__confidence" :title="`Classifier confidence: ${confidenceLabel(item.confidence)}`">
              {{ confidenceLabel(item.confidence) }} confidence
            </span>
          </button>
        </li>
      </ul>

      <aside class="slo-panel__detail" aria-live="polite">
        <template v-if="selected">
          <div class="slo-panel__detail-head">
            <div>
              <span>Selected sample</span>
              <h3>{{ selected.displayName }}</h3>
            </div>
            <span class="slo-panel__badge" :data-review="selected.reviewRequired">
              {{ selected.reviewRequired ? 'Needs review' : selected.primaryLabel }}
            </span>
          </div>
          <dl>
            <div><dt>Category</dt><dd>{{ selected.category || 'Not assigned' }}</dd></div>
            <div><dt>Subcategory</dt><dd>{{ selected.subcategory || 'Not assigned' }}</dd></div>
            <div><dt>Evidence</dt><dd>{{ selected.evidenceSource }}</dd></div>
            <div><dt>Source</dt><dd>{{ selected.userOverridden ? 'User override' : 'Automatic' }}</dd></div>
            <div><dt>Confidence</dt><dd>{{ confidenceLabel(selected.confidence) }}</dd></div>
            <div><dt>State</dt><dd>{{ selected.classificationState }}</dd></div>
          </dl>
          <p v-if="selected.uncertaintyReason" class="slo-panel__reason">
            <strong>Why review?</strong> {{ selected.uncertaintyReason }}.
          </p>
          <div v-if="selected.tags.length" class="slo-panel__tags" aria-label="Tags">
            <span v-for="tag in selected.tags" :key="tag">{{ tag }}</span>
          </div>
          <p class="slo-panel__version">Model {{ selected.modelVersion || '—' }} · Taxonomy {{ selected.taxonomyVersion || '—' }}</p>
        </template>
        <div v-else class="slo-panel__detail-empty">
          <strong>Select a sample</strong>
          <span>Inspect its classification, provenance and uncertainty.</span>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useSloClassification } from '../../composables/useSloClassification'

const {
  response, status, error, search, category, reviewOnly, selected, mockMode,
  categories, filteredItems, load,
} = useSloClassification()

function confidenceLabel(value: number) {
  if (value >= 0.8) return 'High'
  if (value >= 0.55) return 'Medium'
  return 'Low'
}

onMounted(load)
</script>

<style scoped lang="less">
.slo-panel {
  height: 100%; overflow: auto; padding: 0.2rem; box-sizing: border-box;
  color: var(--text-color); background: var(--surface-bg);
  &__header { display: flex; justify-content: space-between; gap: 0.2rem; align-items: flex-start; }
  &__header h2 { margin: 0.03rem 0 0.04rem; font-size: 0.25rem; }
  &__header p { margin: 0; max-width: 7rem; color: var(--muted-text); font-size: 0.13rem; }
  &__eyebrow { color: #5a72d8; font-size: 0.1rem; font-weight: 700; letter-spacing: 0.12em; }
  &__header-actions { display: flex; gap: 0.08rem; align-items: center; }
  &__mock, &__badge, &__item-status { border-radius: 999px; padding: 0.04rem 0.08rem; font-size: 0.1rem; font-weight: 700; }
  &__mock { color: #344ca8; background: #e8edff; }
  &__retry, &__state button { border: 1px solid var(--input-border); border-radius: 0.08rem; background: var(--input-bg); color: var(--text-color); padding: 0.07rem 0.11rem; cursor: pointer; }
  button:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid #7590ff; outline-offset: 2px; }
  &__summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.1rem; margin: 0.18rem 0 0.12rem; }
  &__summary div { padding: 0.12rem; border: 1px solid var(--floating-border); border-radius: 0.1rem; background: var(--floating-bg); }
  &__summary strong, &__summary span { display: block; }
  &__summary strong { font-size: 0.21rem; } &__summary span { color: var(--muted-text); font-size: 0.1rem; }
  &__filters { display: grid; grid-template-columns: 2fr 1fr auto; gap: 0.1rem; align-items: end; margin-bottom: 0.12rem; }
  &__filters label > span { display: block; margin-bottom: 0.04rem; color: var(--muted-text); font-size: 0.1rem; }
  &__filters input[type='search'], &__filters select { width: 100%; box-sizing: border-box; border: 1px solid var(--input-border); border-radius: 0.07rem; background: var(--input-bg); color: var(--input-text); padding: 0.08rem; }
  &__check { display: flex; align-items: center; gap: 0.06rem; min-height: 0.34rem; white-space: nowrap; }
  &__check > span { margin: 0 !important; color: var(--text-color) !important; }
  &__content { display: grid; grid-template-columns: minmax(3.5rem, 1.4fr) minmax(2.5rem, 0.8fr); gap: 0.12rem; min-height: 3.5rem; }
  &__list { list-style: none; margin: 0; padding: 0; border: 1px solid var(--floating-border); border-radius: 0.1rem; overflow: hidden; }
  &__list li + li { border-top: 1px solid var(--floating-border); }
  &__list button { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto 1.05rem; gap: 0.1rem; align-items: center; padding: 0.1rem; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
  &__list button:hover, &__list button.is-selected { background: var(--floating-bg-hover); }
  &__item-main strong, &__item-main span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  &__item-main span, &__confidence { color: var(--muted-text); font-size: 0.1rem; }
  &__item-status { color: #285f47; background: #dff5e9; }
  &__item-status[data-review='true'], &__badge[data-review='true'] { color: #7c3d12; background: #ffead7; }
  &__detail { border: 1px solid var(--floating-border); border-radius: 0.1rem; padding: 0.14rem; background: var(--floating-bg); }
  &__detail-head { display: flex; justify-content: space-between; gap: 0.08rem; align-items: flex-start; }
  &__detail-head span, &__version { color: var(--muted-text); font-size: 0.1rem; }
  &__detail h3 { margin: 0.02rem 0 0.1rem; font-size: 0.17rem; overflow-wrap: anywhere; }
  &__badge { color: #285f47 !important; background: #dff5e9; white-space: nowrap; }
  dl { margin: 0; } dl div { display: flex; justify-content: space-between; gap: 0.1rem; padding: 0.055rem 0; border-bottom: 1px solid var(--floating-border); }
  dt { color: var(--muted-text); } dd { margin: 0; text-align: right; text-transform: capitalize; }
  &__reason { padding: 0.09rem; border-left: 3px solid #e08b42; background: #fff5e9; color: #563316; }
  &__tags { display: flex; flex-wrap: wrap; gap: 0.05rem; margin-top: 0.1rem; }
  &__tags span { padding: 0.035rem 0.065rem; border-radius: 0.05rem; background: var(--file-card-bg); font-size: 0.1rem; }
  &__version { margin-top: 0.12rem; }
  &__detail-empty, &__state { min-height: 2.5rem; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.07rem; color: var(--muted-text); text-align: center; }
  &__state--error { border: 1px solid #e2a26f; border-radius: 0.1rem; background: #fff8f1; color: #6d3b16; }
  &__spinner { width: 0.2rem; height: 0.2rem; border: 2px solid var(--floating-border); border-top-color: #5a72d8; border-radius: 50%; animation: spin 0.8s linear infinite; }
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .slo-panel { &__header, &__content { grid-template-columns: 1fr; display: grid; } &__header-actions { justify-content: space-between; } &__summary { grid-template-columns: repeat(2, 1fr); } &__filters { grid-template-columns: 1fr; } &__list button { grid-template-columns: minmax(0, 1fr) auto; } &__confidence { grid-column: 1 / -1; } }
}
</style>
