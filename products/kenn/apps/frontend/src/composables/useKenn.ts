import { computed, ref, shallowRef } from 'vue'
import {
  askKenn,
  confirmKennAction,
  undoKennAction,
  fetchKennSessionCard,
  type KennActionProposal,
  type KennActionReceipt,
  type KennAdviceFinding,
  type KennSessionTrack,
  type KennSource,
} from '../api/kenn'
import { ApiError } from '../api/client'

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
  actionStatus?: 'pending' | 'requires_confirmation' | 'applying' | 'applied' | 'undoing' | 'undone' | 'rejected' | 'error'
  actionError?: string
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

function getOrCreateSessionId(): string {
  const key = 'kenn_session_id'
  try {
    const existing = localStorage.getItem(key)
    if (existing) return existing
    const id = crypto.randomUUID()
    localStorage.setItem(key, id)
    return id
  } catch {
    return `sess-${Date.now()}`
  }
}

function mapSessionToProject(
  tracks: KennSessionTrack[],
  status: string,
  rawSession?: Record<string, unknown>
): KennProjectInfo {
  const sessionStatus = status || ''
  if (sessionStatus === 'connected' && tracks.length) {
    const focus =
      tracks.find((t) => t.soloed) ||
      tracks.find((t) => t.armed) ||
      tracks[0]
    const effects = (focus?.devices || [])
      .map((d) => String(d?.name || '').trim())
      .filter(Boolean)
    const raw = rawSession || {}
    const bpm = raw.tempo != null ? `${raw.tempo}` : '120'
    const key = raw.scale_name ? `${raw.scale_name}` : '—'
    const sessionName = String(raw.session_name ?? raw.set_name ?? raw.name ?? '').trim()
    return {
      name: sessionName || 'Ableton Live Session',
      daw: 'Ableton Live 12',
      bpm,
      key,
      focusTrack: String(focus?.name || '—'),
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
const sessionId = getOrCreateSessionId()

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

async function sendMessage(text: string) {
  const question = text.trim()
  if (!question || sending.value) return

  error.value = ''
  const userMsg: KennUserMessage = { id: newId('user'), role: 'user', text: question }
  messages.value = [...messages.value, userMsg]

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

    const { answer, suggestions, sources, findings, proposal } = await askKenn({
      question,
      sessionId,
      history: history.slice(0, -1),
    })
    messages.value = [
      ...messages.value,
      {
        id: newId('assistant'),
        role: 'assistant',
        text: answer,
        suggestions: suggestions.length ? suggestions : undefined,
        sources: sources.length ? sources : undefined,
        findings: findings.length ? findings : undefined,
        proposal: proposal || undefined,
        actionStatus: proposal ? 'pending' : undefined,
      },
    ]
  } catch (e) {
    const msg =
      e instanceof ApiError && e.message
        ? e.message
        : e instanceof Error
          ? e.message
          : 'KENN request failed'
    error.value = msg
    messages.value = [
      ...messages.value,
      { id: newId('assistant'), role: 'assistant', text: `Error: ${msg}` },
    ]
  } finally {
    sending.value = false
  }
}

async function applyMessageProposal(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId) as KennAssistantMessage | undefined
  if (!msg || !msg.proposal?.confirmation_token) return

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
    lastActionAt.value = new Date()
    messages.value = [...messages.value]
    await refreshSessionCard()
  } catch (e) {
    msg.actionStatus = 'pending'
    msg.actionError = e instanceof Error ? e.message : 'Action failed to apply — tap Apply to retry.'
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
    msg.actionStatus = 'error'
    msg.actionError = e instanceof Error ? e.message : 'Action failed to undo'
    messages.value = [...messages.value]
  }
}

function rejectMessageProposal(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId) as KennAssistantMessage | undefined
  if (!msg?.proposal || msg.actionStatus === 'applied') return
  msg.actionStatus = 'rejected'
  msg.actionError = undefined
  lastActionAt.value = new Date()
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
