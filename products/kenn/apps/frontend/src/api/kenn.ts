/** KENN 聊天 / Ableton session-card（经 Dashboard /kenn/api 代理） */

import { getApiBase, ApiError, parseApiErrorMessage } from './client'
import { API_PATHS } from './paths'
import { ensureAuthSession, withCsrf } from './mixReview'

async function parseJson(res: Response): Promise<Record<string, unknown>> {
  return (await res.json().catch(() => ({}))) as Record<string, unknown>
}

export type KennSource = {
  label: string
  kind?: string
  score?: number
}

export type KennAdviceFinding = {
  title: string
  severity: 'info' | 'warning' | 'critical'
  confidence?: number
  detail: string
  listeningTest?: string
}

export type KennActionProposal = {
  schema?: string
  action: string
  operation?: string
  target?: string
  track_index?: number
  track_name?: string
  parameter?: string
  device_name?: string
  device_index?: number
  before?: unknown
  after?: unknown
  unit?: string
  reason?: string
  confirmation_token?: string
  evidence?: string[]
  is_rack_synthesis?: boolean
  rack_key?: string
  macro_count?: number
  variations?: string[]
  is_doctor_remediation?: boolean
  remedy_type?: string
  predicted_metrics?: PredictedRemediationMetrics
  is_midi_proposal?: boolean
  scale?: string
  style?: string
  notes?: MidiNote[]
}

export type KennActionReceipt = {
  receipt_id: string
  action: string
  status: string
  verified: boolean
  readback?: unknown
  undo?: {
    proposal?: KennActionProposal
  }
}

export type KennAskResult = {
  answer: string
  /** 跟进提问（related_questions / suggestions） */
  suggestions: string[]
  /** 检索来源；招呼类常为空 */
  sources: KennSource[]
  /** Read-only mix/session findings; never grants mutation authority. */
  findings: KennAdviceFinding[]
  /** DAW 变更提案 */
  proposal?: KennActionProposal
  confirmationToken?: string
  requiresConfirmation?: boolean
  raw: Record<string, unknown>
}

function normalizeSeverity(value: unknown): KennAdviceFinding['severity'] {
  const severity = String(value ?? '').toLowerCase()
  if (['critical', 'high', 'error'].includes(severity)) return 'critical'
  if (['warning', 'warn', 'medium'].includes(severity)) return 'warning'
  return 'info'
}

function normalizeConfidence(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  return Math.max(0, Math.min(1, value > 1 ? value / 100 : value))
}

function findingFrom(raw: unknown): KennAdviceFinding | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const item = raw as Record<string, unknown>
  const title = String(item.title ?? item.label ?? item.type ?? 'Listening check').trim()
  const detail = String(
    item.explanation ?? item.description ?? item.message ?? item.detail ?? item.reason ?? ''
  ).trim()
  const listeningTest = String(
    item.suggested_listening_test ?? item.suggestedAction ?? item.fix_action ?? ''
  ).trim()
  if (!detail && !listeningTest) return undefined
  return {
    title: title.replace(/_/g, ' '),
    severity: normalizeSeverity(item.severity),
    confidence: normalizeConfidence(item.confidence),
    detail: detail || listeningTest,
    listeningTest: listeningTest || undefined,
  }
}

/** Extract only known, bounded advisory collections from the chat contract. */
export function parseAdviceFindings(data: Record<string, unknown>): KennAdviceFinding[] {
  const collections: unknown[][] = []
  const add = (value: unknown) => {
    if (Array.isArray(value)) collections.push(value.slice(0, 6))
  }

  const toolResult = data.tool_result
  if (toolResult && typeof toolResult === 'object') {
    add((toolResult as Record<string, unknown>).findings)
  }
  const orchestration = data.orchestration
  if (orchestration && typeof orchestration === 'object') {
    const orch = orchestration as Record<string, unknown>
    add(orch.findings)
    const report = orch.report
    if (report && typeof report === 'object') {
      const reportData = report as Record<string, unknown>
      const mixingDoctor = reportData.mixing_doctor as Record<string, unknown> | undefined
      const projectHealth = reportData.project_health as Record<string, unknown> | undefined
      const pluginBus = reportData.plugin_bus as Record<string, unknown> | undefined
      add(mixingDoctor?.alerts)
      add(projectHealth?.recommendations)
      add(pluginBus?.recommendations)
    }
  }

  const seen = new Set<string>()
  const findings: KennAdviceFinding[] = []
  for (const collection of collections) {
    for (const raw of collection) {
      const finding = findingFrom(raw)
      if (!finding) continue
      const key = `${finding.title.toLowerCase()}|${finding.detail.toLowerCase()}`
      if (seen.has(key)) continue
      seen.add(key)
      findings.push(finding)
      if (findings.length >= 8) return findings
    }
  }
  return findings
}

export type KennSessionTrack = {
  index?: number
  name?: string
  volume?: number
  pan?: number
  muted?: boolean
  soloed?: boolean
  armed?: boolean
  devices?: Array<{ name?: string }>
}

export type KennSessionCard = {
  ok: boolean
  status?: string
  message?: string
  tracks: KennSessionTrack[]
  raw: Record<string, unknown>
}

function parseSuggestions(data: Record<string, unknown>): string[] {
  const fromRelated = Array.isArray(data.related_questions)
    ? data.related_questions.map((q) => String(q ?? '').trim()).filter(Boolean)
    : []
  if (fromRelated.length) return fromRelated

  const envelope = data.envelope
  if (envelope && typeof envelope === 'object') {
    const result = (envelope as Record<string, unknown>).result
    if (result && typeof result === 'object') {
      const suggestions = (result as Record<string, unknown>).suggestions
      if (Array.isArray(suggestions)) {
        return suggestions
          .map((item) => {
            if (typeof item === 'string') return item.trim()
            if (item && typeof item === 'object') {
              return String((item as Record<string, unknown>).label ?? '').trim()
            }
            return ''
          })
          .filter(Boolean)
      }
    }
  }
  return []
}

function parseSources(data: Record<string, unknown>): KennSource[] {
  if (!Array.isArray(data.sources)) return []
  const out: KennSource[] = []
  for (const item of data.sources) {
    if (!item || typeof item !== 'object') continue
    const s = item as Record<string, unknown>
    const label = String(s.label ?? s.title ?? s.source ?? '').trim()
    if (!label) continue
    const kind = String(s.kind ?? '').trim()
    const source: KennSource = { label }
    if (kind) source.kind = kind
    if (typeof s.score === 'number') source.score = s.score
    out.push(source)
  }
  return out
}

/** POST /kenn/api/ask（非流式，便于侧栏展示） */
export async function askKenn(params: {
  question: string
  sessionId: string
  history?: Array<{ role: string; content: string }>
}): Promise<KennAskResult> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.ask}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      question: params.question,
      limit: 8,
      history: params.history ?? [],
      session_id: params.sessionId,
      stream: false,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  const answer = String(data.answer ?? data.error ?? '').trim()
  const orchResult = (data.orchestration && typeof data.orchestration === 'object')
    ? ((data.orchestration as Record<string, unknown>).result as Record<string, unknown> | undefined)
    : undefined
  const rawProposal = (data.proposal || orchResult?.proposal) as Record<string, unknown> | undefined
  const proposal: KennActionProposal | undefined = rawProposal
    ? {
        ...rawProposal,
        schema: String(rawProposal.schema || ''),
        action: String(rawProposal.action || rawProposal.operation || 'live_action'),
        operation: String(rawProposal.operation || ''),
        target: String(rawProposal.target || 'ableton_track'),
        track_index: typeof rawProposal.track_index === 'number' ? rawProposal.track_index : undefined,
        track_name: String(rawProposal.track_name || ''),
        device_name: rawProposal.device_name != null ? String(rawProposal.device_name) : undefined,
        device_index: typeof rawProposal.device_index === 'number' ? rawProposal.device_index : undefined,
        parameter: String(rawProposal.parameter || ''),
        before: rawProposal.before,
        after: rawProposal.after,
        unit: String(rawProposal.unit || ''),
        reason: String(rawProposal.reason || ''),
        confirmation_token: String(rawProposal.confirmation_token || data.confirmation_token || ''),
        evidence: Array.isArray(rawProposal.evidence) ? rawProposal.evidence.map(String) : [],
      }
    : undefined

  const confirmationToken = String(proposal?.confirmation_token || data.confirmation_token || '').trim()

  return {
    answer: answer || '(empty reply)',
    suggestions: parseSuggestions(data),
    sources: parseSources(data),
    findings: parseAdviceFindings(data),
    proposal,
    confirmationToken: confirmationToken || undefined,
    requiresConfirmation: Boolean(data.requires_confirmation || proposal),
    raw: data,
  }
}

/** POST /kenn/api/ableton/command: 确认执行 DAW 提案 */
export async function confirmKennAction(params: {
  proposal: KennActionProposal
  confirmToken: string
  sessionId: string
}): Promise<{ ok: boolean; status: string; answer?: string; receipt?: KennActionReceipt; error?: string }> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.command}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      command: 'confirm',
      confirm_token: params.confirmToken,
      proposal: params.proposal,
      session_id: params.sessionId,
      idempotency_key: `web-confirm-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    }),
  })
  const data = await parseJson(res)
  if (data.status === 'requires_confirmation') {
    return {
      ok: false,
      status: 'requires_confirmation',
      answer: String(data.answer || 'Explicit confirmation is required.'),
      error: undefined,
    }
  }
  if (!res.ok && data.error) {
    throw new ApiError(String(data.error), res.status)
  }
  const execution = (data.execution && typeof data.execution === 'object') ? (data.execution as Record<string, unknown>) : {}
  const receipt = (data.receipt || execution.receipt) as KennActionReceipt | undefined
  return {
    ok: Boolean(data.status === 'applied' || data.ok || execution.ok),
    status: String(data.status || 'applied'),
    answer: String(data.answer || execution.answer || ''),
    receipt,
    error: data.error ? String(data.error) : undefined,
  }
}

/** 撤销上一步 DAW 变更 (via POST /kenn/api/ableton/osc/undo) */
export async function undoKennAction(params: {
  receipt: KennActionReceipt
  sessionId: string
}): Promise<{ ok: boolean; status: string; answer?: string; receipt?: KennActionReceipt; error?: string }> {
  await ensureAuthSession()
  const base = getApiBase()

  // Phase 1: Request inverse undo proposal
  const propRes = await fetch(`${base}${API_PATHS.kenn.undo}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      session_id: params.sessionId,
      receipt: params.receipt,
    }),
  })
  const propData = await parseJson(propRes)
  if (!propRes.ok || !propData.proposal) {
    throw new ApiError(parseApiErrorMessage(propData, 'Undo proposal failed'), propRes.status)
  }
  const undoProposal = propData.proposal as Record<string, unknown>
  const token = String(undoProposal.confirmation_token || '')

  // Phase 2: Execute verified inverse action
  const execRes = await fetch(`${base}${API_PATHS.kenn.undo}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      session_id: params.sessionId,
      receipt: params.receipt,
      proposal: undoProposal,
      confirm_token: token,
      idempotency_key: String(undoProposal.action_id || `undo-${Date.now()}`),
    }),
  })
  const execData = await parseJson(execRes)
  if (!execRes.ok) {
    throw new ApiError(parseApiErrorMessage(execData, 'Undo execution failed'), execRes.status)
  }
  return {
    ok: Boolean(execData.ok),
    status: 'undone',
    answer: 'Live action reverted.',
    receipt: execData.receipt as KennActionReceipt | undefined,
  }
}

/** GET Ableton 会话卡片（Mixing Doctor 缓存；未连 Live 时可能为空） */
export async function fetchKennSessionCard(): Promise<KennSessionCard> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.sessionCard}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  const session = (data.session && typeof data.session === 'object'
    ? data.session
    : {}) as Record<string, unknown>
  const tracks = Array.isArray(session.tracks) ? (session.tracks as KennSessionTrack[]) : []
  return {
    ok: Boolean(data.ok),
    status: String(session.status ?? ''),
    message: String(session.message ?? '').trim() || undefined,
    tracks,
    raw: data,
  }
}

export type KennPluginParameters = {
  assistant_mode: string
  target_lufs: number
  analysis_enabled: boolean
  live_context_enabled: boolean
}

/** GET 插件参数 (via GET /kenn/api/plugin/parameters) */
export async function fetchPluginParameters(sessionId: string): Promise<KennPluginParameters> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.parameters}?session_id=${encodeURIComponent(sessionId)}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  return (data.parameters || {}) as KennPluginParameters
}

/** POST 更新插件参数 (via POST /kenn/api/plugin/parameters) */
export async function updatePluginParameter(params: {
  sessionId: string
  parameter: string
  value: unknown
}): Promise<{ ok: boolean; parameter: string; value: unknown }> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.parameters}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      session_id: params.sessionId,
      parameter: params.parameter,
      value: params.value,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, 'Parameter update failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    parameter: String(data.parameter),
    value: data.value,
  }
}

/* ==========================================================================
   KENN v0.5 Studio Co-Producer Types & Endpoints
   ========================================================================== */

export type ProRackMacro = {
  index: number
  name: string
  min: number
  max: number
  default: number
  unit: string
}

export type ProRackVariation = {
  name: string
  macros: Record<string, number>
}

export type ProRackDefinition = {
  key: string
  name: string
  description: string
  tags: string[]
  target_role: string
  chains: string[]
  macros: ProRackMacro[]
  variations: Record<string, ProRackVariation>
}

export type DoctorIssue = {
  code: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  track_index: number
  track_name: string
  description: string
  conflict_track_index?: number
  conflict_track_name?: string
  frequency_hz?: number
  gain_recommendation_db?: number
  q_recommendation?: number
}

export type PredictedRemediationMetrics = {
  masking_reduction_percent: number
  headroom_reclaimed_db: number
  mono_correlation_delta: number
}

export type DoctorAuditReport = {
  ok: boolean
  track_count: number
  issues_found: number
  summary: string
  issues: DoctorIssue[]
}

export type DoctorRemediationProposal = {
  schema?: string
  action: string
  track_index: number
  track_name: string
  remedy_type: string
  target_device: string
  parameters: Record<string, unknown>
  predicted_metrics: PredictedRemediationMetrics
  confirmation_token: string
}

export type MidiNote = {
  pitch: number
  start_time: number
  duration: number
  velocity: number
  mute?: boolean
}

export type WorldModelTrack = {
  track_index: number
  name: string
  role: string
  confidence: number
  devices: string[]
}

export type WorldModelSession = {
  tracks: WorldModelTrack[]
  arrangement: {
    energy_curve?: number[]
    current_section?: string
    density_score?: number
  }
  harmonic_context: {
    detected_scale?: string
    confidence?: number
  }
}

/** GET /api/racks - Fetch all 12 pro dynamic racks */
export async function fetchProRacks(): Promise<ProRackDefinition[]> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.racks}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, 'Failed to fetch pro racks'), res.status)
  }
  return (Array.isArray(data.racks) ? data.racks : []) as ProRackDefinition[]
}

/** POST /api/racks/synthesize - Synthesize a pro rack to Ableton */
export async function synthesizeProRack(params: {
  rackKey: string
  trackIndex: number
  snapshotKey?: string
  confirmToken?: string
}): Promise<{ ok: boolean; status: string; answer?: string; confirmation_token?: string }> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.synthesizeRack}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      rack_key: params.rackKey,
      track_index: params.trackIndex,
      snapshot: params.snapshotKey || 'A',
      confirm_token: params.confirmToken,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok && !data.confirmation_token) {
    throw new ApiError(parseApiErrorMessage(data, 'Rack synthesis failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    status: String(data.status || 'applied'),
    answer: data.answer ? String(data.answer) : undefined,
    confirmation_token: data.confirmation_token ? String(data.confirmation_token) : undefined,
  }
}

/** GET /api/session/world_model - Fetch live session intelligence */
export async function fetchSessionWorldModel(): Promise<WorldModelSession | null> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.worldModel}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok || !data.world_model) {
    return null
  }
  return data.world_model as WorldModelSession
}

/** GET /api/session/doctor/audit - Audit live session for masking & clashes */
export async function fetchDoctorAudit(): Promise<DoctorAuditReport> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.doctorAudit}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, 'Doctor audit failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    track_count: Number(data.track_count || 0),
    issues_found: Number(data.issues_found || 0),
    summary: String(data.summary || ''),
    issues: (Array.isArray(data.issues) ? data.issues : []) as DoctorIssue[],
  }
}

/** POST /api/session/doctor/remediate - Execute surgical masking remediation */
export async function remediateDoctorIssue(params: {
  issueCode: string
  trackIndex: number
  confirmToken?: string
}): Promise<{
  ok: boolean
  status: string
  proposal?: DoctorRemediationProposal
  predicted_metrics?: PredictedRemediationMetrics
  confirmation_token?: string
}> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.doctorRemediate}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      issue_code: params.issueCode,
      track_index: params.trackIndex,
      confirm_token: params.confirmToken,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok && !data.confirmation_token) {
    throw new ApiError(parseApiErrorMessage(data, 'Doctor remediation failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    status: String(data.status || 'applied'),
    proposal: data.proposal as DoctorRemediationProposal | undefined,
    predicted_metrics: data.predicted_metrics as PredictedRemediationMetrics | undefined,
    confirmation_token: data.confirmation_token ? String(data.confirmation_token) : undefined,
  }
}

/** POST /api/midi/groove - Apply AudioGen groove humanization */
export async function applyMidiGroove(params: {
  notes: MidiNote[]
  template: 'lofi_swing' | 'hiphop_boombap' | 'edm_shuffle'
  swingPct?: number
  laidbackMs?: number
  jitterPct?: number
}): Promise<{ ok: boolean; notes: MidiNote[]; groove_applied: string }> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.midiGroove}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      notes: params.notes,
      template: params.template,
      swing_pct: params.swingPct ?? 35,
      laidback_ms: params.laidbackMs ?? 6,
      jitter_pct: params.jitterPct ?? 15,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, 'Groove processing failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    notes: (Array.isArray(data.notes) ? data.notes : []) as MidiNote[],
    groove_applied: String(data.groove_applied || params.template),
  }
}

/** POST /api/midi/bassline - Synthesize harmonic bassline */
export async function generateMidiBassline(params: {
  scale?: string
  style?: string
  bars?: number
}): Promise<{ ok: boolean; notes: MidiNote[]; scale: string; style: string }> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.midiBassline}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      scale: params.scale || 'F:minor',
      style: params.style || 'rolling_16th',
      bars: params.bars ?? 2,
    }),
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, 'Bassline generation failed'), res.status)
  }
  return {
    ok: Boolean(data.ok),
    notes: (Array.isArray(data.notes) ? data.notes : []) as MidiNote[],
    scale: String(data.scale || params.scale),
    style: String(data.style || params.style),
  }
}

/** GET /api/genre_curves - Fetch available genre target curve profiles */
export async function fetchGenreCurves(): Promise<string[]> {
  await ensureAuthSession()
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.kenn.genreCurves}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) return ['edm', 'hiphop', 'pop', 'rock', 'techno']
  return (Array.isArray(data.genres) ? data.genres : []) as string[]
}
