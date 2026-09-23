<template>
  <div class="kenn-action-card" :class="`kenn-action-card--${cardStatus}`">
    <!-- Card Header -->
    <div class="kenn-action-card__header">
      <div class="kenn-action-card__badge-group">
        <span class="kenn-action-card__action-badge">
          {{ formattedActionName }}
        </span>
        <span class="kenn-action-card__target-badge">
          {{ proposal.track_name || `Track ${proposal.track_index != null ? proposal.track_index + 1 : ''}` }}
        </span>
      </div>
      <span class="kenn-action-card__status-tag" :class="`kenn-action-card__status-tag--${cardStatus}`">
        {{ statusLabel }}
      </span>
    </div>

    <!-- Parameter Change Diff / Specialized Co-Producer Content -->
    <div class="kenn-action-card__body">
      <!-- 1. Pro Rack Synthesis Proposal -->
      <div v-if="proposal.is_rack_synthesis" class="kenn-action-card__pro-section">
        <div class="kenn-action-card__pro-title-row">
          <strong class="kenn-action-card__pro-title">{{ proposal.rack_key?.replace(/_/g, ' ').toUpperCase() }}</strong>
          <span class="kenn-action-card__tag">8 Macros Auto-Mapped</span>
        </div>
        <div v-if="proposal.variations && proposal.variations.length" class="kenn-action-card__variations-row">
          <span class="kenn-action-card__sub-label">Snapshots:</span>
          <span v-for="v in proposal.variations" :key="v" class="kenn-action-card__var-chip">
            {{ v }}
          </span>
        </div>
      </div>

      <!-- 2. Surgical Doctor Remediation Proposal -->
      <div v-else-if="proposal.is_doctor_remediation" class="kenn-action-card__pro-section">
        <div class="kenn-action-card__pro-title-row">
          <strong class="kenn-action-card__pro-title">{{ proposal.remedy_type?.replace(/_/g, ' ').toUpperCase() }}</strong>
          <span class="kenn-action-card__tag">EQ Eight Surgical Carve</span>
        </div>
        <div v-if="proposal.predicted_metrics" class="kenn-action-card__metrics-row">
          <span class="kenn-action-card__metric-badge kenn-action-card__metric-badge--masking">
            📉 -{{ proposal.predicted_metrics.masking_reduction_percent }}% Masking
          </span>
          <span class="kenn-action-card__metric-badge kenn-action-card__metric-badge--headroom">
            🎚️ +{{ proposal.predicted_metrics.headroom_reclaimed_db }} dB Headroom
          </span>
          <span class="kenn-action-card__metric-badge kenn-action-card__metric-badge--mono">
            🌐 +{{ proposal.predicted_metrics.mono_correlation_delta }} Correlation
          </span>
        </div>
      </div>

      <!-- 3. Neural MIDI Proposal -->
      <div v-else-if="proposal.is_midi_proposal" class="kenn-action-card__pro-section">
        <div class="kenn-action-card__pro-title-row">
          <strong class="kenn-action-card__pro-title">{{ proposal.scale || 'Scale' }}</strong>
          <span class="kenn-action-card__tag">{{ proposal.style || 'Groove' }}</span>
        </div>
        <div class="kenn-action-card__midi-meta">
          <span>AudioGen Groove Humanized</span>
        </div>
      </div>

      <!-- 4. Default Parameter Diff -->
      <div v-else class="kenn-action-card__diff-row">
        <span class="kenn-action-card__param-label">{{ paramLabel }}:</span>
        <span class="kenn-action-card__val-before">{{ formattedBefore }}</span>
        <span class="kenn-action-card__arrow">→</span>
        <span class="kenn-action-card__val-after">{{ formattedAfter }}</span>
      </div>

      <p v-if="proposal.reason" class="kenn-action-card__reason">
        {{ proposal.reason }}
      </p>
      <p v-if="errorMessage && cardStatus !== 'undo_refused'" class="kenn-action-card__error">
        {{ errorMessage }}
      </p>
    </div>

    <!-- Card Actions Footer -->
    <div class="kenn-action-card__footer">
      <button
        v-if="cardStatus === 'pending' || cardStatus === 'requires_confirmation' || cardStatus === 'error'"
        type="button"
        class="kenn-action-card__btn kenn-action-card__btn--apply"
        @click="$emit('apply')"
      >
        <svg class="kenn-action-card__btn-icon" viewBox="0 0 24 24" fill="none">
          <path d="M5 12L10 17L20 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        Apply to Live 12
      </button>
      <button
        v-if="cardStatus === 'pending' || cardStatus === 'requires_confirmation' || cardStatus === 'error'"
        type="button"
        class="kenn-action-card__btn kenn-action-card__btn--reject"
        @click="$emit('reject')"
      >
        Dismiss
      </button>

      <button
        v-else-if="cardStatus === 'applying'"
        type="button"
        class="kenn-action-card__btn kenn-action-card__btn--applying"
        disabled
      >
        <span class="kenn-action-card__spinner"></span>
        Verifying in Live 12...
      </button>

      <div v-else-if="cardStatus === 'applied'" class="kenn-action-card__applied-group">
        <span class="kenn-action-card__applied-msg">
          <svg class="kenn-action-card__check-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
          </svg>
          Readback Verified
        </span>
        <button
          type="button"
          class="kenn-action-card__btn kenn-action-card__btn--undo"
          @click="$emit('undo')"
        >
          <svg class="kenn-action-card__btn-icon" viewBox="0 0 24 24" fill="none">
            <path d="M3 10H14C17.3137 10 20 12.6863 20 16C20 19.3137 17.3137 22 14 22H9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            <path d="M7 6L3 10L7 14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Undo
        </button>
      </div>

      <div v-else-if="cardStatus === 'undone'" class="kenn-action-card__applied-group">
        <span class="kenn-action-card__undone-msg">
          Restored to Original State
        </span>
      </div>
      <div v-else-if="cardStatus === 'undo_refused'" class="kenn-action-card__applied-group">
        <span class="kenn-action-card__undone-msg">{{ errorMessage || 'Not undone. Nothing changed.' }}</span>
      </div>
      <div v-else-if="cardStatus === 'rejected'" class="kenn-action-card__applied-group">
        <span class="kenn-action-card__undone-msg">Proposal Dismissed — No Changes Made</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { KennActionProposal, KennActionReceipt } from '../api/kenn'

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

const formattedActionName = computed(() => {
  const act = props.proposal.action || props.proposal.operation || 'Live Action'
  switch (act) {
    case 'set_mute':
      return 'MUTE TRACK'
    case 'set_solo':
      return 'SOLO TRACK'
    case 'set_volume':
      return 'VOLUME ADJUST'
    case 'set_pan':
      return 'PAN ADJUST'
    case 'set_arm':
      return 'ARM TRACK'
    case 'rename_track':
      return 'RENAME TRACK'
    case 'insert_device':
      return 'INSERT DEVICE'
    case 'remove_device':
      return 'REMOVE DEVICE'
    case 'gain_staging':
      return 'GAIN STAGE'
    case 'group_tracks':
      return 'BUS GROUP'
    case 'synthesize_pro_rack':
      return 'PRO RACK SYNTHESIS'
    case 'remediate_masking':
      return 'SURGICAL MASKING REMEDY'
    case 'generate_midi_bassline':
      return 'NEURAL MIDI GENERATION'
    default:
      return act.replace(/_/g, ' ').toUpperCase()
  }
})

const paramLabel = computed(() => {
  const p = props.proposal.parameter || props.proposal.action
  if (p === 'muted') return 'Mute'
  if (p === 'soloed') return 'Solo'
  if (p === 'volume') return 'Fader Volume'
  if (p === 'pan') return 'Stereo Pan'
  if (p === 'insert_device' || props.proposal.action === 'insert_device') return 'Device'
  if (p === 'remove_device' || props.proposal.action === 'remove_device') return 'Device'
  if (p === 'gain_staging' || props.proposal.action === 'gain_staging') return 'Gain Staging'
  if (p === 'group_tracks' || props.proposal.action === 'group_tracks') return 'Bus Group'
  return p
})

function formatVal(v: unknown, param?: string): string {
  if (typeof v === 'boolean') return v ? 'ON' : 'OFF'
  if (typeof v === 'number') {
    if (param === 'volume') return v.toFixed(2)
    if (param === 'pan') return v === 0 ? 'Center' : v > 0 ? `R ${Math.round(v * 100)}` : `L ${Math.round(Math.abs(v) * 100)}`
    return v.toString()
  }
  return String(v ?? '—')
}

const formattedBefore = computed(() => {
  if (props.proposal.action === 'insert_device') {
    return '(None)'
  }
  if (props.proposal.action === 'remove_device') {
    return String(props.proposal.device_name || 'Device')
  }
  return formatVal(props.proposal.before, props.proposal.parameter)
})

const formattedAfter = computed(() => {
  if (props.proposal.action === 'insert_device') {
    return String(props.proposal.device_name || 'Device')
  }
  if (props.proposal.action === 'remove_device') {
    return '(Removed)'
  }
  return formatVal(props.proposal.after, props.proposal.parameter)
})

const statusLabel = computed(() => {
  switch (props.cardStatus) {
    case 'pending':
    case 'requires_confirmation':
      return 'Ready to Apply'
    case 'applying':
      return 'Applying...'
    case 'applied':
      return 'Live 12 Synced'
    case 'undoing':
      return 'Undoing...'
    case 'undone':
      return 'Reverted'
    case 'undo_refused':
      return 'Live 12 Synced'
    case 'rejected':
      return 'Dismissed'
    case 'error':
      return 'Failed'
    default:
      return 'Proposal'
  }
})
</script>

<style scoped lang="less">
.kenn-action-card {
  margin-top: 10px;
  background: rgba(24, 24, 27, 0.95);
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 8px;
  padding: 12px 14px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  transition: all 0.2s ease-in-out;

  &--applied {
    border-color: rgba(16, 185, 129, 0.45);
    background: rgba(16, 185, 129, 0.06);
  }

  &--undone {
    border-color: rgba(113, 113, 122, 0.4);
    opacity: 0.85;
  }

  &--rejected {
    border-color: rgba(113, 113, 122, 0.4);
    opacity: 0.82;
  }

  &--error {
    border-color: rgba(239, 68, 68, 0.5);
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  &__badge-group {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  &__action-badge {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 2px 7px;
    border-radius: 4px;
    background: rgba(245, 158, 11, 0.2);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.4);
    white-space: nowrap;
  }

  &__target-badge {
    font-size: 12px;
    font-weight: 600;
    color: #e4e4e7;
    background: rgba(255, 255, 255, 0.07);
    padding: 2px 8px;
    border-radius: 4px;
    white-space: nowrap;
  }

  &__status-tag {
    font-size: 11px;
    font-weight: 500;
    color: #a1a1aa;
    white-space: nowrap;
    flex-shrink: 0;
    margin-left: auto;

    &--applied {
      color: #10b981;
      font-weight: 600;
    }
    &--requires_confirmation {
      color: #f59e0b;
      font-weight: 600;
    }
    &--error {
      color: #ef4444;
    }
  }

  &__body {
    padding: 6px 0 10px;
  }

  &__diff-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  &__param-label {
    color: #a1a1aa;
    font-family: inherit;
  }

  &__val-before {
    color: #71717a;
    text-decoration: line-through;
  }

  &__arrow {
    color: #f59e0b;
    font-weight: 700;
  }

  &__val-after {
    color: #38bdf8;
    font-weight: 700;
  }

  &__pro-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 4px;
  }

  &__pro-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  &__pro-title {
    font-size: 13px;
    color: #f4f4f5;
    font-weight: 600;
  }

  &__tag {
    font-size: 10px;
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 600;
  }

  &__variations-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
  }

  &__sub-label {
    color: #71717a;
  }

  &__var-chip {
    background: rgba(255, 255, 255, 0.08);
    color: #d4d4d8;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 10px;
  }

  &__metrics-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
  }

  &__metric-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;

    &--masking {
      background: rgba(239, 68, 68, 0.15);
      color: #fca5a5;
    }
    &--headroom {
      background: rgba(16, 185, 129, 0.15);
      color: #6ee7b7;
    }
    &--mono {
      background: rgba(59, 130, 246, 0.15);
      color: #93c5fd;
    }
  }

  &__midi-meta {
    font-size: 11px;
    color: #a1a1aa;
  }

  &__reason {
    margin-top: 6px;
    font-size: 12px;
    color: #a1a1aa;
    line-height: 1.4;
  }

  &__error {
    margin-top: 6px;
    font-size: 12px;
    color: #ef4444;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  &__btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;

    &--apply {
      background: #f59e0b;
      color: #18181b;
      border: 1px solid #d97706;

      &:hover:not(:disabled) {
        background: #fbbf24;
        box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
      }
    }

    &--applying {
      background: rgba(245, 158, 11, 0.4);
      color: #18181b;
      border: none;
      cursor: wait;
    }

    &--reject {
      background: transparent;
      color: #a1a1aa;
      border: 1px solid rgba(255, 255, 255, 0.14);

      &:hover {
        color: #f4f4f5;
        border-color: rgba(255, 255, 255, 0.28);
      }
    }

    &--undo {
      background: rgba(255, 255, 255, 0.08);
      color: #e4e4e7;
      border: 1px solid rgba(255, 255, 255, 0.15);

      &:hover {
        background: rgba(255, 255, 255, 0.14);
        color: #fff;
      }
    }

    &-icon {
      width: 14px;
      height: 14px;
    }
  }

  &__applied-group {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    justify-content: space-between;
  }

  &__applied-msg {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    font-weight: 600;
    color: #10b981;
  }

  &__undone-msg {
    font-size: 12px;
    color: #71717a;
    font-style: italic;
  }

  &__check-icon {
    width: 16px;
    height: 16px;
  }

  &__spinner {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(24, 24, 27, 0.3);
    border-top-color: #18181b;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
