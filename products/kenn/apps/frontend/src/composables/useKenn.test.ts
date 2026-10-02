import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/kenn', () => ({
  askKenn: vi.fn(),
  getAnswerUpgrade: vi.fn(),
  confirmKennAction: vi.fn(),
  undoKennAction: vi.fn(),
  fetchKennSessionCard: vi.fn().mockResolvedValue({
    ok: true,
    status: 'offline',
    tracks: [],
    raw: {},
  }),
}))

import { askKenn, confirmKennAction, fetchKennSessionCard, getAnswerUpgrade, undoKennAction } from '../api/kenn'
import { useKenn } from './useKenn'

const mockedAsk = vi.mocked(askKenn)
const mockedConfirm = vi.mocked(confirmKennAction)
const mockedUndo = vi.mocked(undoKennAction)
const mockedSessionCard = vi.mocked(fetchKennSessionCard)
const mockedUpgrade = vi.mocked(getAnswerUpgrade)

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


describe('useKenn answer upgrades', () => {
  const kenn = useKenn()
  const base = { suggestions: [], sources: [], findings: [], raw: {} }

  beforeEach(() => {
    kenn.messages.value = []
    mockedAsk.mockReset()
    mockedUpgrade.mockReset()
  })

  afterEach(() => vi.useRealTimers())

  it('shows the template at once, then swaps in the accepted model answer', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValue({ ...base, answer: 'Template answer.', answerUpgrade: { id: 'u1', pollMs: 500 } })
    mockedUpgrade
      .mockResolvedValueOnce({ status: 'pending' })
      .mockResolvedValueOnce({ status: 'accepted', answer: 'Fuller model answer.' })

    await kenn.sendMessage('How do I tame harsh hats?')
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'Template answer.', upgrade: 'pending' })

    await vi.advanceTimersByTimeAsync(1100)
    expect(mockedUpgrade).toHaveBeenCalledWith('u1', expect.any(String))
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'Fuller model answer.', upgraded: true })
    expect(kenn.messages.value.at(-1)).not.toHaveProperty('upgrade', 'pending')
    vi.useRealTimers()
  })

  it('keeps the in-your-Live line when the model answer replaces the template', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValue({
      ...base, answer: 'Template answer.', answerUpgrade: { id: 'u3', pollMs: 500 },
      raw: { your_set: { line: 'In your Live, built in: EQ Eight.' } },
    })
    mockedUpgrade.mockResolvedValueOnce({ status: 'accepted', answer: 'Fuller model answer.' })

    await kenn.sendMessage('How do I EQ the bass?')
    await vi.advanceTimersByTimeAsync(600)
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'Fuller model answer.\n\nIn your Live, built in: EQ Eight.' })
    vi.useRealTimers()
  })

  it('keeps the template when the model answer is rejected', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValue({ ...base, answer: 'Template answer.', answerUpgrade: { id: 'u2', pollMs: 500 } })
    mockedUpgrade.mockResolvedValueOnce({ status: 'rejected' })

    await kenn.sendMessage('What does Drum Buss do?')
    await vi.advanceTimersByTimeAsync(600)
    const last = kenn.messages.value.at(-1)
    expect(last).toMatchObject({ text: 'Template answer.' })
    expect(last?.role === 'assistant' && last.upgraded).toBeFalsy()
    expect(last?.role === 'assistant' && last.upgrade).toBeFalsy()
    vi.useRealTimers()
  })

  it('discards an in-flight upgrade when the producer asks the next question', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValueOnce({ ...base, answer: 'First template.', answerUpgrade: { id: 'old', pollMs: 500 } })
    let finish!: (result: { status: 'accepted'; answer: string }) => void
    mockedUpgrade.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    await kenn.sendMessage('How do I EQ the vocal?')
    const first = kenn.messages.value.at(-1)
    await vi.advanceTimersByTimeAsync(500)

    mockedAsk.mockResolvedValueOnce({ ...base, answer: 'Next answer.' })
    await kenn.sendMessage('What about the bass?')
    finish({ status: 'accepted', answer: 'Late vocal advice.' })
    await vi.advanceTimersByTimeAsync(500)

    expect(kenn.messages.value.find((m) => m.id === first?.id)).toMatchObject({ text: 'First template.', upgrade: undefined })
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'Next answer.' })
    expect(mockedUpgrade).toHaveBeenCalledTimes(1)
  })

  it('stops polling a removed message before the next request', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValueOnce({ ...base, answer: 'Template.', answerUpgrade: { id: 'removed', pollMs: 500 } })
    await kenn.sendMessage('How does EQ work?')
    kenn.messages.value = []
    await vi.advanceTimersByTimeAsync(1000)
    expect(mockedUpgrade).not.toHaveBeenCalled()
    expect(kenn.messages.value).toEqual([])
  })

  it('replaces template sources with the accepted answer sources, including an empty list', async () => {
    vi.useFakeTimers()
    mockedAsk.mockResolvedValueOnce({ ...base, answer: 'Template.', sources: [{ label: 'Template note' }], answerUpgrade: { id: 'sources', pollMs: 500 } })
    mockedUpgrade.mockResolvedValueOnce({ status: 'accepted', answer: 'Model answer.', sources: [] })
    await kenn.sendMessage('How does EQ work?')
    await vi.advanceTimersByTimeAsync(500)
    expect(kenn.messages.value.at(-1)).toMatchObject({ text: 'Model answer.', sources: undefined })
  })
})
