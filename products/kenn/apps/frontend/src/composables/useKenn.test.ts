import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/kenn', () => ({
  askKenn: vi.fn(),
  confirmKennAction: vi.fn(),
  undoKennAction: vi.fn(),
  fetchKennSessionCard: vi.fn().mockResolvedValue({
    ok: true,
    status: 'offline',
    tracks: [],
    raw: {},
  }),
}))

import { askKenn, confirmKennAction, fetchKennSessionCard, undoKennAction } from '../api/kenn'
import { useKenn } from './useKenn'

const mockedAsk = vi.mocked(askKenn)
const mockedConfirm = vi.mocked(confirmKennAction)
const mockedUndo = vi.mocked(undoKennAction)
const mockedSessionCard = vi.mocked(fetchKennSessionCard)

describe('useKenn investor-facing failure states', () => {
  const kenn = useKenn()

  beforeEach(() => {
    kenn.messages.value = []
    kenn.error.value = ''
    kenn.lastActionAt.value = null
    mockedAsk.mockReset()
    mockedConfirm.mockReset()
  })

  it('renders a bounded safe sentence instead of arbitrary JavaScript error text', async () => {
    mockedAsk.mockRejectedValue(new Error('private implementation detail'))

    await kenn.sendMessage('How many tracks do I have?')

    expect(kenn.error.value).toBe("KENN couldn't complete that request safely. Nothing changed; try again.")
    expect(kenn.messages.value.at(-1)).toMatchObject({
      role: 'assistant',
      text: "KENN couldn't complete that request safely. Nothing changed; try again.",
    })
  })

  it('shows a visible no-change error when a proposal has no confirmation token', async () => {
    kenn.messages.value = [{
      id: 'proposal-without-token',
      role: 'assistant',
      proposal: { action: 'set_mute', track_name: 'Bass' },
      actionStatus: 'pending',
    }]

    await kenn.applyMessageProposal('proposal-without-token')

    expect(kenn.messages.value[0]).toMatchObject({
      actionStatus: 'error',
      actionError: 'This proposal is missing its confirmation token. Ask KENN to prepare a fresh proposal; nothing changed.',
    })
    expect(mockedConfirm).not.toHaveBeenCalled()
  })

  it('does not report a dismissed proposal as a Live action', () => {
    kenn.messages.value = [{
      id: 'dismissed-proposal',
      role: 'assistant',
      proposal: { action: 'set_mute', confirmation_token: 'token' },
      actionStatus: 'pending',
    }]

    kenn.rejectMessageProposal('dismissed-proposal')

    expect(kenn.messages.value[0]).toMatchObject({ actionStatus: 'rejected' })
    expect(kenn.lastActionAt.value).toBeNull()
  })
})

describe('useKenn receipt and project state', () => {
  const kenn = useKenn()

  beforeEach(() => {
    kenn.messages.value = []
    mockedConfirm.mockReset()
    mockedUndo.mockReset()
  })

  it('never re-offers Apply when a receipt undo is refused as stale', async () => {
    kenn.messages.value = [{
      id: 'eq', role: 'assistant', actionStatus: 'applied',
      proposal: { action: 'set_device_parameter', track_name: 'Bass' },
      receipt: { receipt_id: 'receipt-9', action: 'set_device_parameter', status: 'applied', verified: true },
    }]
    mockedUndo.mockRejectedValue(new Error('Live device parameter changed since the receipt; undo is stale.'))

    await kenn.undoMessageProposal('eq')

    expect(kenn.messages.value[0]).toMatchObject({
      actionStatus: 'undo_refused',
      actionError: 'Not undone: Live has changed since this action (it may already have been undone). Nothing changed.',
    })
  })

  it('marks the reverted card undone when a chat undo proposal is applied', async () => {
    kenn.messages.value = [
      { id: 'eq', role: 'assistant', actionStatus: 'applied',
        proposal: { action: 'set_device_parameter', track_name: 'Bass' }, receipt: { receipt_id: 'receipt-9', action: 'set_device_parameter', status: 'applied', verified: true } },
      { id: 'undo', role: 'assistant', actionStatus: 'pending', undoOfReceiptId: 'receipt-9',
        proposal: { action: 'set_device_parameter', track_name: 'Bass', confirmation_token: 'token' } },
    ]
    mockedConfirm.mockResolvedValue({ ok: true, status: 'applied', receipt: { receipt_id: 'receipt-10', action: 'set_device_parameter', status: 'applied', verified: true } })

    await kenn.applyMessageProposal('undo')

    expect(kenn.messages.value[0]).toMatchObject({ actionStatus: 'undone' })
    expect(kenn.messages.value[1]).toMatchObject({ actionStatus: 'applied' })
  })

  it('shows the selected track as focus and the full Live key', async () => {
    mockedSessionCard.mockResolvedValueOnce({
      ok: true, status: 'connected',
      tracks: [{ index: 0, name: 'Kick' }, { index: 3, name: 'Drum Bus', devices: [{ name: 'Compressor' }] }],
      raw: { session: { tempo: 120, root_note: 0, scale_name: 'Major', selected_track_index: 3 } },
    })

    await kenn.refreshSessionCard()

    expect(kenn.project.value).toMatchObject({ focusTrack: 'Drum Bus', key: 'C Major', effects: ['Compressor'] })
  })
})
