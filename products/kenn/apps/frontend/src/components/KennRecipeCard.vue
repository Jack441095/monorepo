<script setup lang="ts">
import { computed } from 'vue'
import type { KennActionProposal, KennActionReceipt, KennActionStep } from '../api/kenn'
import { formatDb } from '../utils/formatLevel'

// A recipe proposal is several changes in one plan -- "turn the hats down 3 dB and the kick up 2 dB". The single
// KennActionCard reads track_name off the proposal, and a recipe carries no track of its own, so before this existed
// every two-step plan rendered a card labelled "Track ". Each step does carry its own track and its own before/after,
// so the plan can be shown as what it is: N named changes, each with the value it would write.
const props = withDefaults(
  defineProps<{
    proposal: KennActionProposal
    cardStatus?: 'pending' | 'requires_confirmation' | 'applying' | 'dismissing' | 'applied' | 'undoing' | 'undone' | 'undo_refused' | 'rejected' | 'unknown' | 'failed' | 'partial' | 'error'
    receipt?: KennActionReceipt
    errorMessage?: string
    // False on a card that is itself an undo. Its receipt reverses the change before it, so "undoing" it would
    // put that change straight back: a redo behind an Undo label (L3 requal, 9 Oct 2026).
    undoable?: boolean
  }>(),
  {
    cardStatus: 'pending',
    receipt: undefined,
    errorMessage: '',
    undoable: true,
  }
)

defineEmits<{
  (e: 'apply'): void
  (e: 'reject'): void
  (e: 'undo'): void
}>()

const steps = computed(() => props.proposal.steps ?? [])

function stepLabel(action: string): string {
  switch (action) {
    case 'set_mute':
      return 'MUTE'
    case 'set_solo':
      return 'SOLO'
    case 'set_volume':
      return 'VOLUME'
    case 'set_pan':
      return 'PAN'
    case 'set_arm':
      return 'ARM'
    case 'rename_track':
      return 'RENAME'
    case 'insert_device':
      return 'ADD DEVICE'
    case 'remove_device':
      return 'REMOVE DEVICE'
    default:
      return action.replace(/_/g, ' ').toUpperCase()
  }
}

function targetLabel(step: KennActionStep): string {
  const track = step.track_name ?? `Track ${(step.track_index ?? 0) + 1}`
  const label = step.target_label ?? (step.device_name ? `${track} / ${step.device_name}` : track)
  const address = step.target_address
  if (!address) return label // Mixer children have no device or rack path to disambiguate.
  // Live's name-only label cannot distinguish duplicate devices or chains; show the observed one-based positions too.
  const bus = address.kind === 'master' ? 'Master' : `${address.kind === 'return' ? 'Return' : 'Track'} ${address.index + 1}`
  const path = address.device_path.map((index, depth) => `${depth % 2 === 0 ? 'device' : 'chain'} ${index + 1}`).join(' / ')
  return `${label} (${bus}, ${path})`
}

function rawValue(value: unknown): string | null {
  // Raw parameter values must not inherit the requested display unit without a measured mapping.
  if (typeof value === 'number' && Number.isFinite(value)) return `${value} raw`
  if (typeof value === 'boolean') return value ? 'On' : 'Off'
  return typeof value === 'string' ? value : null
}

function transition(step: KennActionStep): string {
  // Device/setup children carry mapped display strings; mixer children carry dB values.
  if (step.before_display && step.after_display) return `${step.before_display} → ${step.after_display}`
  const before = formatDb(step.before_db) ?? rawValue(step.before)
  const after = formatDb(step.after_db) ?? rawValue(step.after)
  // Missing observations remain explicit instead of inventing a reviewable value.
  return before === null || after === null ? 'value to be confirmed' : `${before} → ${after}`
}
</script>

<template>
  <div class="kenn-recipe-card" :data-status="cardStatus">
    <header class="kenn-recipe-card__head">
      <span class="kenn-recipe-card__title">{{ steps.length }} changes</span>
      <span class="kenn-recipe-card__badge">PLAN</span>
    </header>

    <ol class="kenn-recipe-card__steps">
      <li v-for="(step, index) in steps" :key="step.action_id ?? index" class="kenn-recipe-card__step">
        <span class="kenn-recipe-card__index">{{ index + 1 }}</span>
        <span class="kenn-recipe-card__track">{{ targetLabel(step) }}</span>
        <span class="kenn-recipe-card__action">{{ step.parameter ?? stepLabel(step.action) }}</span>
        <span class="kenn-recipe-card__transition">{{ transition(step) }}</span>
      </li>
    </ol>

    <p v-if="(cardStatus === 'pending' || cardStatus === 'requires_confirmation' || cardStatus === 'dismissing' || cardStatus === 'rejected') && steps.length" class="kenn-recipe-card__note">
      Nothing has changed yet.
    </p>
    <p v-if="cardStatus === 'partial'" class="kenn-recipe-card__note">Partially applied. Inspect Live before preparing another change.</p>
    <p v-if="cardStatus === 'failed'" class="kenn-recipe-card__note">Action failed. Review the receipt before preparing a fresh proposal.</p>
    <p v-if="cardStatus === 'unknown'" class="kenn-recipe-card__note">
      Outcome unknown. Inspect Live before preparing another change.
    </p>
    <p v-if="cardStatus === 'applied'" class="kenn-recipe-card__note">Readback verified.</p>
    <p v-if="cardStatus === 'undone'" class="kenn-recipe-card__note">Observed before-state restored.</p>

    <div class="kenn-recipe-card__actions">
      <button v-if="cardStatus === 'dismissing'" class="kenn-recipe-card__btn" disabled>
        Dismissing...
      </button>
      <button
        v-if="cardStatus === 'pending' || cardStatus === 'requires_confirmation'"
        class="kenn-recipe-card__btn kenn-recipe-card__btn--apply"
        @click="$emit('apply')"
      >
        Apply all {{ steps.length }} to Live 12
      </button>
      <button
        v-if="cardStatus === 'applied' && receipt && undoable"
        class="kenn-recipe-card__btn kenn-recipe-card__btn--undo"
        @click="$emit('undo')"
      >
        Undo the plan
      </button>
      <button
        v-if="cardStatus === 'pending' || cardStatus === 'requires_confirmation'"
        class="kenn-recipe-card__btn kenn-recipe-card__btn--reject"
        @click="$emit('reject')"
      >
        Not now
      </button>
    </div>

    <p v-if="errorMessage" class="kenn-recipe-card__error">{{ errorMessage }}</p>
  </div>
</template>

<style scoped>
.kenn-recipe-card {
  border: 1px solid var(--kenn-border, rgba(255, 255, 255, 0.14));
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kenn-recipe-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kenn-recipe-card__title {
  font-weight: 600;
}
.kenn-recipe-card__badge {
  font-size: 11px;
  letter-spacing: 0.08em;
  opacity: 0.7;
}
.kenn-recipe-card__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kenn-recipe-card__step {
  display: grid;
  grid-template-columns: 20px 1fr auto auto;
  gap: 8px;
  align-items: baseline;
  font-size: 13px;
}
.kenn-recipe-card__index {
  opacity: 0.6;
}
.kenn-recipe-card__action {
  font-size: 11px;
  letter-spacing: 0.06em;
  opacity: 0.75;
}
.kenn-recipe-card__transition {
  font-variant-numeric: tabular-nums;
  opacity: 0.9;
}
.kenn-recipe-card__note {
  margin: 0;
  font-size: 12px;
  opacity: 0.7;
}
.kenn-recipe-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.kenn-recipe-card__btn {
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}
.kenn-recipe-card__error {
  margin: 0;
  font-size: 12px;
  color: #e0655f;
}
</style>
