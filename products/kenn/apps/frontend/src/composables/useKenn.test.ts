import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/kenn', () => ({
  askKenn: vi.fn(),
  confirmKennAction: vi.fn(),
  undoKennAction: vi.fn(),
  fetchKennBrainAnswer: vi.fn(),
  fetchKennSessionCard: vi.fn().mockResolvedValue({
    ok: true,
    status: 'offline',
    tracks: [],
    raw: {},
  }),
}))

import {
  askKenn,
  confirmKennAction,
  fetchKennBrainAnswer,
  fetchKennSessionCard,
  undoKennAction,
} from '../api/kenn'
import { useKenn } from './useKenn'

const mockedAsk = vi.mocked(askKenn)
const mockedBrain = vi.mocked(fetchKennBrainAnswer)
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


describe('useKenn project card with a return selected', () => {
  it('names the selected return track instead of falling back to track 1', async () => {
    const kenn = useKenn()
    mockedSessionCard.mockResolvedValueOnce({
      ok: true, status: 'connected',
      tracks: [{ index: 0, name: 'Kick' }],
      raw: { session: { tempo: 120, root_note: 0, scale_name: 'Major', selected_track_index: null,
                        selected_track_kind: { kind: 'return', index: 0, name: 'A-Reverb' } } },
    })
    await kenn.refreshSessionCard()
    expect(kenn.project.value.focusTrack).toBe('A-Reverb')
  })
})

describe('useKenn template first, model answer later', () => {
  const kenn = useKenn()
  const templateReply = {
    answer: 'template answer',
    suggestions: [],
    sources: [],
    findings: [],
    proposal: undefined,
    raw: { brain_pending: { job_id: 'abc123' } },
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', globalThis) // useKenn's sleep() reaches for window.setTimeout; tests run in node
    kenn.messages.value = []
    mockedAsk.mockReset()
    mockedBrain.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows the template at once and swaps in the model answer when it is ready', async () => {
    mockedAsk.mockResolvedValue(templateReply as never)
    mockedBrain
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValueOnce({ status: 'ready', answer: 'model answer' })

    await kenn.sendMessage('how do I sidechain the bass?')
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'template answer' })

    await vi.advanceTimersByTimeAsync(2100)
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'model answer' })
  })

  it('keeps the in-your-Live line when the model answer replaces the template', async () => {
    mockedAsk.mockResolvedValue({
      ...templateReply,
      raw: { brain_pending: { job_id: 'abc123' }, your_set: { line: 'In your Live, built in: EQ Eight.' } },
    } as never)
    mockedBrain.mockResolvedValue({ status: 'ready', answer: 'model answer' })

    await kenn.sendMessage('how do I EQ the bass?')
    await vi.advanceTimersByTimeAsync(1100)

    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'model answer\n\nIn your Live, built in: EQ Eight.' })
  })

  it('keeps the template when the rewrite was rejected', async () => {
    mockedAsk.mockResolvedValue(templateReply as never)
    mockedBrain.mockResolvedValue({ status: 'rejected' })

    await kenn.sendMessage('how do I sidechain the bass?')
    await vi.advanceTimersByTimeAsync(3000)

    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'template answer' })
    expect(mockedBrain).toHaveBeenCalledTimes(1)
  })

  it('never polls for a reply that carries a Live proposal', async () => {
    mockedAsk.mockResolvedValue({
      ...templateReply,
      proposal: { action: 'set_mute', confirmation_token: 'token' },
    } as never)

    await kenn.sendMessage('mute the bass')
    await vi.advanceTimersByTimeAsync(3000)

    expect(mockedBrain).not.toHaveBeenCalled()
  })
})
