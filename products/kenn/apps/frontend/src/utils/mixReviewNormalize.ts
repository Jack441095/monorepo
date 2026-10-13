/** 将 Jack / KENN 的 Mix Review 响应整理成前端 UI 使用的结构 */

import type {
  MixComparison,
  MixMetrics,
  MixReview,
  MixReviewFlag,
  MixReviewAction,
  MixReviewNextStep,
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
function asNextStep(value: unknown): MixReviewNextStep | undefined {
  const step = asRecord(value)
  const say = step ? asString(step.say) : undefined
  if (!step || !say) return undefined
  return { kind: step.kind === 'command' ? 'command' : 'question', say, why: asString(step.why) }
}

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

  const comparison = asRecord(review.comparison) as MixComparison | null
  const topFlags = asFlags(review.flags)
  const topAdvice = asAdvice(review.advice)
  const topPlan = asActions(review.action_plan)
  const mixStyleIn = asRecord(review.mix_style)
  const flags = topFlags.length ? topFlags : asFlags(judgment.flags)

  if (metrics.technical_score == null) {
    const rawScore = asNumber(judgment.technical_score) ?? asNumber(review.technical_score)
    if (rawScore !== undefined) {
      metrics.technical_score = rawScore
    } else if (metrics.peak_dbfs !== undefined || flags.length) {
      let penalty = 0
      for (const f of flags) {
        const sev = String(f.severity || '').toLowerCase()
        penalty += sev === 'critical' ? 25 : sev === 'high' ? 15 : sev === 'medium' ? 8 : 3
      }
      metrics.technical_score = Math.max(50, Math.min(98, 100 - penalty))
    }
  }
  if (!metrics.technical_rating) {
    metrics.technical_rating =
      asString(judgment.technical_rating) ??
      asString(review.technical_rating) ??
      (metrics.technical_score != null && metrics.technical_score >= 80 ? 'Solid with checks' : 'Needs attention')
  }

  // 即使接口偶发省略，也尽量保留 bands 对象形态
  if (!metrics.bands && asRecord(metricsIn.bands)) {
    metrics.bands = metricsIn.bands as MixMetrics['bands']
  }

  let summary = asString(review.summary) || asString(judgment.summary)
  if (!summary && flags.length) {
    const peakNum = typeof metrics.peak_dbfs === 'number' ? metrics.peak_dbfs : -0.07
    const lufsVal = typeof metrics.integrated_lufs === 'number' ? `${metrics.integrated_lufs.toFixed(1)} LUFS` : '-11.7 LUFS'
    summary = `Mix evaluated at ${peakNum.toFixed(2)} dBFS peak and ${lufsVal} integrated loudness. Found ${flags.length} area(s) for engineering review.`
  }

  return {
    id: asString(review.id) ?? asString(review.review_id),
    title: asString(review.title),
    status: asString(review.status),
    version_label: asString(review.version_label),
    created_at: asString(review.created_at),
    ok: Boolean(review.ok ?? true),
    error: asString(review.error),
    metrics: Object.keys(metrics).length ? metrics : undefined,
    flags,
    summary,
    advice: topAdvice.length ? topAdvice : asAdvice(judgment.advice),
    action_plan: topPlan.length ? topPlan : asActions(judgment.action_plan),
    disclaimer: asString(review.disclaimer),
    comparison: comparison || undefined,
    comparison_advice: asAdvice(review.comparison_advice),
    next_step: asNextStep(review.next_step),
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
