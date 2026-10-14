/** 将 Jack / KENN 的 Mix Review 响应整理成前端 UI 使用的结构 */

import type {
  MixComparison,
  MixGrade,
  MixGradePart,
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

/**
 * Keeps the backend's grade only if it has the numbers the card needs. A half-formed grade is dropped rather than
 * patched up: the card would otherwise show a score the server never computed.
 */
function asGrade(value: unknown): MixGrade | undefined {
  const g = asRecord(value)
  const points = g ? asNumber(g.points) : undefined
  const available = g ? asNumber(g.points_available) : undefined
  const fullMarks = g ? asNumber(g.full_marks) : undefined
  if (!g || points === undefined || available === undefined || fullMarks === undefined) return undefined
  const parts = (Array.isArray(g.parts) ? g.parts : []).filter((p) => asRecord(p)) as MixGradePart[]
  const ungraded = (Array.isArray(g.ungraded) ? g.ungraded : [])
    .map((u) => asRecord(u))
    .filter((u): u is Record<string, unknown> => !!u)
    .map((u) => ({ part: String(u.part ?? ''), reason: String(u.reason ?? '') }))
  return { points, points_available: available, full_marks: fullMarks, meaning: asString(g.meaning) ?? '', parts, ungraded }
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
 * 顶层缺少 summary/flags 时，从 judgment 回填。分数只取后端给的 grade，不在前端估算。
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

  // 即使接口偶发省略，也尽量保留 bands 对象形态
  if (!metrics.bands && asRecord(metricsIn.bands)) {
    metrics.bands = metricsIn.bands as MixMetrics['bands']
  }

  let summary = asString(review.summary) || asString(judgment.summary)
  if (!summary && flags.length) {
    // Only quote figures the analyser actually returned. Falling back to a made-up peak or LUFS here once put
    // numbers on screen that no file had produced, so a missing reading is left out of the sentence.
    const readings: string[] = []
    if (typeof metrics.peak_dbfs === 'number') readings.push(`${metrics.peak_dbfs.toFixed(2)} dBFS peak`)
    if (typeof metrics.integrated_lufs === 'number') readings.push(`${metrics.integrated_lufs.toFixed(1)} LUFS integrated loudness`)
    const measured = readings.length ? `Mix measured at ${readings.join(' and ')}. ` : ''
    summary = `${measured}Found ${flags.length} area(s) for engineering review.`
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
    grade: asGrade(review.grade),
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
