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
    cardStatus?: 'pending' | 'requires_confirmation' | 'applying' | 'applied' | 'undoing' | 'undone' | 'undo_refused' | 'rejected' | 'error'
    receipt?: KennActionReceipt
    errorMessage?: string
  }>(),
  {
    cardStatus: 'pending',
    receipt: undefined,
    errorMessage: '',
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

// before_db/after_db are the numbers a producer can act on ("-14.0 dB -> -17.0 dB"). Fall back to the raw values when
// the backend could not produce a dB figure, because a step with no before/after shown is worse than a plain one.
function transition(step: KennActionStep): string {
  const unit = step.unit === 'normalized' ? '' : step.unit ? ` ${step.unit}` : ''
  const { before_db: before, after_db: after } = step
  if (before === null || before === undefined || after === null || after === undefined) {
    return 'value to be confirmed'
  }
  return `${formatDb(before)} → ${formatDb(after)}${unit}`
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
        <span class="kenn-recipe-card__track">{{ step.track_name ?? `Track ${(step.track_index ?? 0) + 1}` }}</span>
        <span class="kenn-recipe-card__action">{{ stepLabel(step.action) }}</span>
        <span class="kenn-recipe-card__transition">{{ transition(step) }}</span>
      </li>
    </ol>

    <p v-if="cardStatus !== 'applied' && steps.length" class="kenn-recipe-card__note">
      Nothing has changed yet.
    </p>

    <div class="kenn-recipe-card__actions">
      <button
        v-if="cardStatus === 'pending' || cardStatus === 'requires_confirmation'"
        class="kenn-recipe-card__btn kenn-recipe-card__btn--apply"
        @click="$emit('apply')"
      >
        Apply all {{ steps.length }} to Live 12
      </button>
      <button
        v-if="cardStatus === 'applied' && receipt"
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