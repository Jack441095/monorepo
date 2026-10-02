import { computed, ref, shallowRef } from 'vue'
import {
  askKenn,
  getAnswerUpgrade,
  confirmKennAction,
  revokeKennConfirmation,
  undoKennAction,
  fetchKennSessionCard,
  type KennActionProposal,
  type KennActionReceipt,
  type KennAdviceFinding,
  type KennSessionTrack,
  type KennSource,
} from '../api/kenn'
import { userFacingKennError } from '../api/client'

export type KennUserMessage = {
  id: string
  role: 'user'
  text: string
}

export type KennAssistantMessage = {
  id: string
  role: 'assistant'
  text?: string
  steps?: string[]
  notes?: Array<{ label: string; text: string }>
  findings?: KennAdviceFinding[]
  sources?: KennSource[]
  suggestions?: string[]
  followUp?: string
  proposal?: KennActionProposal
  receipt?: KennActionReceipt
  actionStatus?: 'pending' | 'requires_confirmation' | 'applying' | 'dismissing' | 'applied' | 'undoing' | 'undone' | 'undo_refused' | 'rejected' | 'error'
  actionError?: string
  undoOfReceiptId?: string
  /** The model is still writing a fuller answer; the template text is showing meanwhile. */
  upgrade?: 'pending'
  /** The text was replaced by the model's answer after KENN's grounding check accepted it. */
  upgraded?: boolean
}

export type KennChatMessage = KennUserMessage | KennAssistantMessage

export type KennProjectInfo = {
  name: string
  daw: string
  bpm: string
  key: string
  focusTrack: string
  effects: string[]
  references: string[]
  connected: boolean
  sessionStatus: string
  trackCount: number
}

const MOCK_MESSAGES: KennChatMessage[] = [
  {
    id: 'user-1',
    role: 'user',
    text: 'How do I saturate sub-bass without clipping?',
  },
  {
    id: 'assistant-1',
    role: 'assistant',
    steps: [
      'Load Ableton Saturator or Dynamic Tube on the sub-bass track.',
      'Set Drive moderately (+2 to +4 dB) with Soft Sine or Analog Clip curve.',
      'Keep Output ceiling at -0.5 dB to prevent inter-sample peaks.',
    ],
    notes: [
      { label: 'Check', text: 'Compare A/B loudness and check low-end mono compatibility below 90 Hz.' },
      { label: 'Avoid this', text: 'Avoid heavy waveshaping or excessive high harmonics that clash with kicks.' },
    ],
    sources: [
      { label: 'Ableton Live 12 Manual - Saturator' },
      { label: 'Mixing Low-End & Headroom Guide' },
    ],
    suggestions: ['add EQ 8 to channel 4', 'What curve works best for 808s?', 'How should I EQ before saturating?'],
  },
]

const MOCK_PROJECT: KennProjectInfo = {
  name: 'Ableton Live Session',
  daw: 'Ableton Live 12',
  bpm: '120',
  key: 'C Major',
  focusTrack: '1-MIDI',
  effects: ['Saturator', 'EQ Eight', 'Limiter'],
  references: ['Ableton Reference Manual', 'Low-End Mix Guide'],
  connected: true,
  sessionStatus: 'connected',
  trackCount: 1,
}

const EMPTY_PROJECT: KennProjectInfo = {
  name: '—',
  daw: 'Ableton Live 12',
  bpm: '—',
  key: '—',
  focusTrack: '—',
  effects: [],
  references: [],
  connected: false,
  sessionStatus: '',
  trackCount: 0,
}

function newId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// One session per page load: chat cards are not persisted across reloads, so
// reusing a stored ID would surface receipts the visible chat no longer shows.
function newSessionId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return newId('sess')
  }
}

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function mapSessionToProject(
  tracks: KennSessionTrack[],
  status: string,
  rawSession?: Record<string, unknown>
): KennProjectInfo {
  const sessionStatus = status || ''
  if (sessionStatus === 'connected' && tracks.length) {
    const selectedIndex = typeof rawSession?.selected_track_index === 'number' ? rawSession.selected_track_index : -1
    const focus =
      tracks.find((t) => t.index === selectedIndex) ||
      tracks.find((t) => t.soloed) ||
      tracks.find((t) => t.armed) ||
      tracks[0]
    // A selected return or master track is not in `tracks`; name it rather
    // than falling back to track 1.
    const kind = rawSession?.selected_track_kind as { kind?: string; name?: string } | undefined
    const busName = kind && (kind.kind === 'return' || kind.kind === 'master')
      ? (kind.kind === 'master' ? 'Master' : String(kind.name || 'Return'))
      : ''
    const effects = (focus?.devices || [])
      .map((d) => String(d?.name || '').trim())
      .filter(Boolean)
    const raw = rawSession || {}
    const bpm = raw.tempo != null ? `${raw.tempo}` : '120'
    const rootNote = typeof raw.root_note === 'number' ? NOTE_NAMES[((raw.root_note % 12) + 12) % 12] : ''
    const key = raw.scale_name ? `${rootNote} ${raw.scale_name}`.trim() : '—'
    const sessionName = String(raw.session_name ?? raw.set_name ?? raw.name ?? '').trim()
    return {
      name: sessionName || 'Ableton Live Session',
      daw: 'Ableton Live 12',
      bpm,
      key,
      focusTrack: busName || String(focus?.name || '—'),
      effects,
      references: [],
      connected: true,
      sessionStatus: 'connected',
      trackCount: tracks.length,
    }
  }
  return {
    ...EMPTY_PROJECT,
    daw: 'Ableton Live 12',
    connected: false,
    sessionStatus,
  }
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

const useMock = ref(import.meta.env.VITE_KENN_USE_MOCK === '1')
const messages = shallowRef<KennChatMessage[]>(useMock.value ? [...MOCK_MESSAGES] : [])
const project = ref<KennProjectInfo>(useMock.value ? { ...MOCK_PROJECT } : { ...EMPTY_PROJECT })
const sending = ref(false)
const error = ref('')
const lastActionAt = ref<Date | null>(null)
const sessionId = newSessionId()
let answerTurn = 0

export async function refreshSessionCard() {
  if (useMock.value) return
  const maxAttempts = 6
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const card = await fetchKennSessionCard()
      const status = card.status || ''
      const rawSession = (card.raw?.session && typeof card.raw.session === 'object')
        ? (card.raw.session as Record<string, unknown>)
        : undefined
      project.value = mapSessionToProject(card.tracks, status, rawSession)
      if (status === 'connected' && card.tracks.length) return
      if (status === 'dispatched' || (status === 'connected' && !card.tracks.length)) {
        if (attempt < maxAttempts - 1) await sleep(1500)
        continue
      }
      return
    } catch {
      if (attempt < maxAttempts - 1) {
        await sleep(1500)
        continue
      }
      project.value = { ...EMPTY_PROJECT, sessionStatus: 'offline' }
    }
  }
}

void refreshSessionCard()

const UPGRADE_WAIT_MS = 90_000

/** Swap in the model's answer once KENN has accepted it; the template stays if it's rejected or never arrives. */
async function waitForUpgrade(messageId: string, upgradeId: string, pollMs: number, turn: number, suffix = '') {
  const currentMessage = () => turn === answerTurn
    ? messages.value.find((m) => m.id === messageId && m.role === 'assistant' && m.upgrade === 'pending') as KennAssistantMessage | undefined
    : undefined
  const settle = (patch: Partial<KennAssistantMessage>) => {
    const msg = currentMessage()
    if (!msg) return
    Object.assign(msg, { upgrade: undefined, ...patch })
    messages.value = [...messages.value]
  }
  const deadline = Date.now() + UPGRADE_WAIT_MS
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, pollMs))
    if (!currentMessage()) return
    let result
    try {
      result = await getAnswerUpgrade(upgradeId, sessionId)
    } catch {
      break
    }
    if (!currentMessage()) return
    if (result.status === 'pending') continue
    if (result.status === 'accepted' && result.answer) {
      settle({ text: `${result.answer}${suffix}`, upgraded: true, sources: result.sources?.length ? result.sources : undefined })
      return
    }
    break
  }
  settle({})
}

async function sendMessage(text: string) {
  const question = text.trim()
  if (!question || sending.value) return

  error.value = ''
  const turn = ++answerTurn
  // The next prompt uses the answer already shown. Changing that older answer
  // later would make the visible history disagree with the submitted history.
  const previous = messages.value.map((m) => m.role === 'assistant' && m.upgrade === 'pending'
    ? { ...m, upgrade: undefined }
    : m)
  const userMsg: KennUserMessage = { id: newId('user'), role: 'user', text: question }
  messages.value = [...previous, userMsg]

  sending.value = true
  try {
    const history = messages.value
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && (m.text || m.steps)))
      .slice(-6)
      .map((m) => ({
        role: m.role,
        content:
          m.role === 'user'
            ? m.text
            : m.text || (m.steps || []).join('\n') || '',
      }))

    const { answer, suggestions, sources, findings, proposal, raw, answerUpgrade } = await askKenn({
      question,
      sessionId,
      history: history.slice(0, -1),
    })
    const assistantId = newId('assistant')
    messages.value = [
      ...messages.value,
      {
        id: assistantId,
        upgrade: answerUpgrade && !proposal ? 'pending' : undefined,
        role: 'assistant',
        text: answer,
        suggestions: suggestions.length ? suggestions : undefined,
        sources: sources.length ? sources : undefined,
        findings: findings.length ? findings : undefined,
        proposal: proposal || undefined,
        actionStatus: proposal ? 'pending' : undefined,
        undoOfReceiptId: proposal && raw?.undo_of_receipt_id ? String(raw.undo_of_receipt_id) : undefined,
      },
    ]
    if (answerUpgrade && !proposal) {
      // The "in your Live" line was added to the template answer; the model's answer doesn't have it, so carry it across.
      const yourSetLine = (raw?.your_set as { line?: unknown } | undefined)?.line
      void waitForUpgrade(assistantId, answerUpgrade.id, answerUpgrade.pollMs, turn, yourSetLine ? `\n\n${String(yourSetLine)}` : '')
    }
  } catch (e) {
    const msg = userFacingKennError(
      e,
      "KENN couldn't complete that request safely. Nothing changed; try again.",
    )
    error.value = msg
    messages.value = [
      ...messages.value,
      { id: newId('assistant'), role: 'assistant', text: msg },
    ]
  } finally {
    sending.value = false
  }
}

async function applyMessageProposal(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId) as KennAssistantMessage | undefined
  if (!msg || !['pending', 'requires_confirmation', 'error'].includes(msg.actionStatus || 'pending')) return
  if (!msg.proposal?.confirmation_token) {
    msg.actionStatus = 'error'
    msg.actionError = 'This proposal is missing its confirmation token. Ask KENN to prepare a fresh proposal; nothing changed.'
    messages.value = [...messages.value]
    return
  }

  msg.actionStatus = 'applying'
  msg.actionError = undefined
  messages.value = [...messages.value]

  try {
    const res = await confirmKennAction({
      proposal: msg.proposal,
      confirmToken: msg.proposal.confirmation_token,
      sessionId,
    })
    if (res.status === 'requires_confirmation') {
      msg.actionStatus = 'requires_confirmation'
      msg.actionError = undefined
      messages.value = [...messages.value]
      return
    }
    if (!res.ok) {
      msg.actionStatus = 'pending'
      msg.actionError = res.error || res.answer || 'Action could not be confirmed — tap Apply to retry.'
      messages.value = [...messages.value]
      return
    }
    msg.receipt = res.receipt
    msg.actionStatus = 'applied'
    if (msg.undoOfReceiptId) {
      const reverted = messages.value.find(
        (m) => m.role === 'assistant' && m.receipt?.receipt_id === msg.undoOfReceiptId,
      ) as KennAssistantMessage | undefined
      if (reverted) reverted.actionStatus = 'undone'
    }
    lastActionAt.value = new Date()
    messages.value = [...messages.value]
    await refreshSessionCard()
  } catch (e) {
    msg.actionStatus = 'pending'
    msg.actionError = userFacingKennError(
      e,
      'KENN could not verify that action. Check Live before retrying; KENN will not send another change automatically.',
    )
    messages.value = [...messages.value]
  }
}

async function undoMessageProposal(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId) as KennAssistantMessage | undefined
  if (!msg || !msg.receipt) return

  msg.actionStatus = 'undoing'
  msg.actionError = undefined
  messages.value = [...messages.value]

  try {
    const res = await undoKennAction({
      receipt: msg.receipt,
      sessionId,
    })
    if (!res.ok) {
      throw new Error(res.error || res.answer || 'Undo could not be completed.')
    }
    msg.actionStatus = 'undone'
    lastActionAt.value = new Date()
    messages.value = [...messages.value]
    await refreshSessionCard()
  } catch (e) {
    // Never fall back to 'error': that state re-offers Apply on an action that already ran.
    msg.actionStatus = 'undo_refused'
    const detail = e instanceof Error ? e.message : ''
    msg.actionError = /stale|changed since/i.test(detail)
      ? 'Not undone: Live has changed since this action (it may already have been undone). Nothing changed.'
      : userFacingKennError(
          e,
          'KENN could not verify the undo. Inspect Live before retrying; no further action was sent.',
        )
    messages.value = [...messages.value]
  }
}

async function rejectMessageProposal(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId) as KennAssistantMessage | undefined
  if (!msg?.proposal || !['pending', 'requires_confirmation', 'error'].includes(msg.actionStatus || 'pending')) return
  if (!msg.proposal.confirmation_token) {
    msg.actionError = 'This proposal is missing its confirmation token. Ask KENN to prepare a fresh proposal before dismissing it.'
    messages.value = [...messages.value]
    return
  }
  const previousStatus = msg.actionStatus || 'pending'
  msg.actionStatus = 'dismissing'
  msg.actionError = undefined
  messages.value = [...messages.value]
  const failedDismissal = 'KENN could not verify dismissal. This proposal may still be pending or already executing; check Live before trying again.'
  try {
    const result = await revokeKennConfirmation({ confirmToken: msg.proposal.confirmation_token, sessionId })
    if (result.ok && result.status === 'revoked') {
      msg.actionStatus = 'rejected'
    } else {
      msg.actionStatus = previousStatus
      msg.actionError = result.error || failedDismissal
    }
  } catch (e) {
    msg.actionStatus = previousStatus
    // A lost revoke response does not tell us whether a concurrent Apply ran.
    msg.actionError = e instanceof TypeError ? failedDismissal : userFacingKennError(e, failedDismissal)
  }
  messages.value = [...messages.value]
}

export function useKenn() {
  return {
    useMock: computed(() => useMock.value),
    messages,
    project,
    sending,
    error,
    lastActionAt,
    sendMessage,
    refreshSessionCard,
    applyMessageProposal,
    undoMessageProposal,
    rejectMessageProposal,
  }
}
