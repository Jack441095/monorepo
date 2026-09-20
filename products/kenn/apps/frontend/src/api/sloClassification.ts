import { ApiError, getApiBase, parseApiErrorMessage } from './client'
import { API_PATHS } from './paths'

export const SLO_CLASSIFICATION_SCHEMA = 'kenn.slo-classifications/v1'

export type SloClassificationState = 'ready' | 'stale' | 'missing'
export type SloServiceStatus = 'loading' | 'ready' | 'empty' | 'offline' | 'unavailable' | 'error'

export type SloClassificationItem = {
  id: string
  displayName: string
  category: string
  subcategory: string
  tags: string[]
  confidence: number
  primaryLabel: string
  reviewRequired: boolean
  uncertaintyReason: string | null
  evidenceSource: string
  winningEvidence: string
  modelVersion: number
  taxonomyVersion: number
  userOverridden: boolean
  classificationState: SloClassificationState
}

export type SloClassificationResponse = {
  schema: typeof SLO_CLASSIFICATION_SCHEMA
  status: 'ready'
  items: SloClassificationItem[]
  summary: { total: number; returned: number; needsReview: number; stale: number }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Malformed SLO classification response.')
  }
  return value as Record<string, unknown>
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value.trim() : fallback
}

function integer(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0
}

function confidence(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 0
}

export function normalizeSloClassificationItem(value: unknown): SloClassificationItem {
  const source = record(value)
  const state = text(source.classification_state)
  const classificationState: SloClassificationState =
    state === 'stale' || state === 'missing' ? state : 'ready'
  const tagSource = text(source.evidence_source, 'unknown')
  const primaryLabel = text(source.primary_label, 'Unclassified')
  return {
    id: text(source.id),
    displayName: text(source.display_name, 'Unnamed sample'),
    category: text(source.category),
    subcategory: text(source.subcategory),
    tags: Array.isArray(source.tags) ? source.tags.map((tag) => text(tag)).filter(Boolean) : [],
    confidence: confidence(source.confidence),
    primaryLabel: primaryLabel === 'Unknown' ? 'Needs review' : primaryLabel,
    reviewRequired: Boolean(source.review_required) || primaryLabel === 'Needs review',
    uncertaintyReason: text(source.uncertainty_reason) || null,
    evidenceSource: tagSource,
    winningEvidence: text(source.winning_evidence, 'UNKNOWN'),
    modelVersion: integer(source.model_version),
    taxonomyVersion: integer(source.taxonomy_version),
    userOverridden: Boolean(source.user_overridden),
    classificationState,
  }
}

export function normalizeSloClassificationResponse(value: unknown): SloClassificationResponse {
  const source = record(value)
  if (source.schema !== SLO_CLASSIFICATION_SCHEMA || source.status !== 'ready' || !Array.isArray(source.items)) {
    throw new Error('Unsupported or malformed SLO classification response.')
  }
  const items = source.items.map(normalizeSloClassificationItem)
  const summary = source.summary && typeof source.summary === 'object'
    ? source.summary as Record<string, unknown>
    : {}
  return {
    schema: SLO_CLASSIFICATION_SCHEMA,
    status: 'ready',
    items,
    summary: {
      total: integer(summary.total ?? items.length),
      returned: integer(summary.returned ?? items.length),
      needsReview: integer(summary.needs_review ?? items.filter((item) => item.reviewRequired).length),
      stale: integer(summary.stale ?? items.filter((item) => item.classificationState === 'stale').length),
    },
  }
}

export function filterSloClassifications(
  items: SloClassificationItem[], query: string, category: string, reviewOnly: boolean,
): SloClassificationItem[] {
  const needle = query.trim().toLocaleLowerCase()
  return items.filter((item) => {
    if (category && item.category !== category) return false
    if (reviewOnly && !item.reviewRequired) return false
    if (!needle) return true
    return [item.displayName, item.primaryLabel, item.category, item.subcategory, ...item.tags]
      .join(' ')
      .toLocaleLowerCase()
      .includes(needle)
  })
}

export async function fetchSloClassifications(signal?: AbortSignal): Promise<SloClassificationResponse> {
  const response = await fetch(`${getApiBase()}${API_PATHS.kenn.sloClassifications}`, {
    credentials: 'include',
    signal,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(parseApiErrorMessage(data, response.statusText), response.status)
  }
  return normalizeSloClassificationResponse(data)
}
