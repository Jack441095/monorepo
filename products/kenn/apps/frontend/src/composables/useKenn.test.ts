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

import { askKenn, confirmKennAction } from '../api/kenn'
import { useKenn } from './useKenn'

const mockedAsk = vi.mocked(askKenn)
const mockedConfirm = vi.mocked(confirmKennAction)

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
