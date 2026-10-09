// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

// The two cards each hide Undo when told to; this file checks the history actually tells them. Only a message that
// came back from "Undo that" carries undoOfReceiptId (useKenn sets it from the backend's undo_of_receipt_id).
const messages = ref<unknown[]>([])
vi.mock('../../composables/useKenn', () => ({
  useKenn: () => ({
    messages,
    sending: ref(false),
    sendMessage: vi.fn(),
    applyMessageProposal: vi.fn(),
    undoMessageProposal: vi.fn(),
    rejectMessageProposal: vi.fn(),
  }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

const { default: KennChatHistory } = await import('../KennChatHistory.vue')

const volume = { action: 'set_volume', track_name: 'Synth', before: 0.6, after: 0.5 }
const recipe = {
  action: 'recipe',
  steps: [{ action: 'set_volume', track_name: 'Synth', before: 0.6, after: 0.5, before_db: -9, after_db: -12 }],
}
const receipt = { receipt_id: 'receipt-1', status: 'applied', verified: true }

function applied(id: string, proposal: object, undoOfReceiptId?: string) {
  return { id, role: 'assistant', text: '', proposal, receipt, actionStatus: 'applied', undoOfReceiptId }
}

describe('KennChatHistory undo cards', () => {
  it('offers Undo on a change but not on the card that undid it', () => {
    messages.value = [
      applied('change', volume),
      applied('undo', volume, 'receipt-0'),
      applied('recipe-change', recipe),
      applied('recipe-undo', recipe, 'receipt-2'),
    ]
    const wrapper = mount(KennChatHistory)
    const undoButtons = (id: number) => wrapper.findAll('.chat-message')[id].findAll('[class*="btn--undo"]').length
    expect([0, 1, 2, 3].map(undoButtons)).toEqual([1, 0, 1, 0])
  })
})
