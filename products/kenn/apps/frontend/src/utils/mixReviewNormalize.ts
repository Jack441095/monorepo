/** 将 Jack / KENN 的 Mix Review 响应整理成前端 UI 使用的结构 */

import type {
  MixComparison,
  MixMetrics,
  MixReview,
  MixReviewFlag,
  MixReviewAction,
} from './mixReviewTypes'

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function asNumber(v: unknown): number | undefined {
  if (v === undefined || v === null || v === '' || v === 'n/a') return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

function asString(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined
}

function asFlags(v: unknown): MixReviewFlag[] {
  if (!Array.isArray(v)) return []
  return v.filter((item) => item && typeof item === 'object') as MixReviewFlag[]
}

function asAdvice(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((item) => String(item)).filter(Boolean)
}

function asActions(v: unknown): MixReviewAction[] {
  if (!Array.isArray(v)) return []
  return v.filter((item) => item && typeof item === 'object') as MixReviewAction[]
}

/** 兼容 `{ review }` 包装，或直接返回 review 本体 */
export function extractReviewPayload(raw: unknown): Record<string, unknown> | null {
  const root = asRecord(raw)
  if (!root) return null
  const nested = asRecord(root.review)
  if (nested && (nested.metrics || nested.judgment || nested.flags || nested.id)) {
    return nested
  }
  if (root.metrics || root.judgment || root.flags || root.id) {
    return root
  }
  return nested || root
}

/**
 * 映射 Jack/KENN 报告 → 左侧工作区用的 MixReview。
 * 顶层缺少 score/rating/summary/flags 时，从 judgment 回填。
 */
export function normalizeMixReview(raw: unknown): MixReview {
  const review = extractReviewPayload(raw)
  if (!review) return {}

  const judgment = asRecord(review.judgment) || {}
  const metricsIn = asRecord(review.metrics) || {}
  const metrics: MixMetrics = { ...(metricsIn as MixMetrics) }

  if (metrics.technical_score == null) {
    metrics.technical_score = asNumber(judgment.technical_score)
  }
  if (!metrics.technical_rating) {
    metrics.technical_rating = asString(judgment.technical_rating)
  }

  // 即使接口偶发省略，也尽量保留 bands 对象形态
  if (!metrics.bands && asRecord(metricsIn.bands)) {
    metrics.bands = metricsIn.bands as MixMetrics['bands']
  }

  const comparison = asRecord(review.comparison) as MixComparison | null
  const topFlags = asFlags(review.flags)
  const topAdvice = asAdvice(review.advice)
  const topPlan = asActions(review.action_plan)
  const mixStyleIn = asRecord(review.mix_style)

  return {
    id: asString(review.id),
    title: asString(review.title),
    status: asString(review.status),
    version_label: asString(review.version_label),
    created_at: asString(review.created_at),
    ok: Boolean(review.ok ?? true),
    error: asString(review.error),
    metrics: Object.keys(metrics).length ? metrics : undefined,
    flags: topFlags.length ? topFlags : asFlags(judgment.flags),
    summary: asString(review.summary) || asString(judgment.summary),
    advice: topAdvice.length ? topAdvice : asAdvice(judgment.advice),
    action_plan: topPlan.length ? topPlan : asActions(judgment.action_plan),
    disclaimer: asString(review.disclaimer),
    comparison: comparison || undefined,
    comparison_advice: asAdvice(review.comparison_advice),
    reference: asRecord(review.reference)
      ? (review.reference as MixReview['reference'])
      : undefined,
    mix_style: mixStyleIn
      ? {
          name: asString(mixStyleIn.name),
          genre: asString(mixStyleIn.genre),
          label: asString(mixStyleIn.label),
          genre_key: asString(mixStyleIn.genre_key),
        }
      : undefined,
  }
}
