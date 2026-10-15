export type KennInsertGradePart = {
  part: 'technical_health' | 'declared_target' | 'reference_match'
  points: number
  points_available: number
  full_marks: number
  left_out: Array<string | { dimension: string; reason: string }>
  note: string
}

export type KennInsertGrade = {
  schema: 'kenn.plugin_insert_grade.v1'
  scope: 'selected_insert_window'
  conversation_id: string
  insert_id: string
  host_track_name: string
  sample_rate: number
  measurement_window: Record<string, unknown> | null
  freshness: { age_seconds: number; max_age_seconds: number; current_for_diagnosis: boolean }
  status: 'graded' | 'ungraded'
  reason: string
  grade: {
    points: number; points_available: number; full_marks: 100; meaning: string
    parts: KennInsertGradePart[]
    ungraded: Array<{ part: string; reason: string }>
  }
  stereo: null | {
    points: number; points_available: 6; points_lost: number; source: string
    tier: string; threshold_band: string; correlation: number
  }
  unscored_dimensions: Array<{ dimension: string; reason: string }>
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 2048 // Characters: explanations remain bounded companion data.
}

function numberIn(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
}

function close(left: number, right: number): boolean {
  return Math.abs(left - right) < 0.001 // Points: only floating-point representation noise is accepted.
}

/** Accept only the selected insert's current partial-grade contract; malformed grades stay unavailable. */
export function parsePluginInsertGrade(value: unknown, owner: string, insert: string, hostName: string): KennInsertGrade | undefined {
  if (!record(value) || value.schema !== 'kenn.plugin_insert_grade.v1' || value.scope !== 'selected_insert_window'
      || value.conversation_id !== owner || value.insert_id !== insert || value.host_track_name !== hostName
      || !numberIn(value.sample_rate, 8000, 384000) || !text(value.reason)
      || (value.status !== 'graded' && value.status !== 'ungraded')) return // Foreign or unknown contracts cannot label this source.
  const freshness = value.freshness
  if (!record(freshness) || !numberIn(freshness.age_seconds, 0, Number.MAX_SAFE_INTEGER)
      || !numberIn(freshness.max_age_seconds, Number.MIN_VALUE, value.status === 'graded' ? 1 : 15)
      || typeof freshness.current_for_diagnosis !== 'boolean') return // Legacy status may last 15 seconds, but cannot grant scored continuous evidence extra life.
  const grade = value.grade
  if (!record(grade) || grade.full_marks !== 100 || !numberIn(grade.points, 0, 6)
      || !numberIn(grade.points_available, 0, 6) || grade.points > grade.points_available || !text(grade.meaning)
      || !Array.isArray(grade.parts) || grade.parts.length > 1
      || !Array.isArray(grade.ungraded) || grade.ungraded.length > 3) return // A partial score must never be rescaled into 100 available points.
  const budgets = { technical_health: 30, declared_target: 30, reference_match: 40 }
  const seen = new Set<string>()
  for (const part of grade.parts) {
    if (!record(part) || typeof part.part !== 'string' || !Object.hasOwn(budgets, part.part) || seen.has(part.part)) return // Each policy part appears exactly once.
    const fullMarks = budgets[part.part as keyof typeof budgets]
    if (part.part !== 'technical_health' || part.full_marks !== fullMarks || part.points_available !== 6
        || !numberIn(part.points, 0, part.points_available) || !Array.isArray(part.left_out) || part.left_out.length > 5
        || !part.left_out.every(item => text(item) || (record(item) && text(item.dimension) && text(item.reason)))
        || !text(part.note)) return // Unsupported target/reference evidence contributes no points.
    seen.add(part.part)
  }
  const parts = grade.parts as KennInsertGradePart[]
  if (!close(parts.reduce((sum, part) => sum + part.points, 0), grade.points)
      || !close(parts.reduce((sum, part) => sum + part.points_available, 0), grade.points_available)) return // Totals must agree with the shown parts.
  for (const item of grade.ungraded) {
    if (!record(item) || !text(item.part) || !Object.hasOwn(budgets, item.part) || seen.has(item.part)
        || !text(item.reason)) return // An omission cannot duplicate a scored or already omitted part.
    seen.add(item.part)
  }
  if (seen.size !== 3) return // Every policy part is either scored or explicitly unavailable.
  if (!Array.isArray(value.unscored_dimensions) || value.unscored_dimensions.length > 5
      || !value.unscored_dimensions.every(item => record(item) && text(item.dimension) && text(item.reason))) return // Render only bounded explanations, never arbitrary nested payloads.
  const window = value.measurement_window
  if (window !== null && !record(window)) return // An unavailable window is explicit, rather than an unchecked scalar.
  if (value.status === 'graded') {
    const stereo = value.stereo
    if (!freshness.current_for_diagnosis || freshness.age_seconds > freshness.max_age_seconds
        || grade.points_available !== 6 || !record(stereo) || stereo.points_available !== 6
        || !numberIn(stereo.points, 0, 6) || !numberIn(stereo.points_lost, 0, 6)
        || !close(stereo.points, grade.points) || !close(stereo.points + stereo.points_lost, 6)
        || !numberIn(stereo.correlation, -1, 1) || !text(stereo.source) || !text(stereo.tier) || !text(stereo.threshold_band)
        || !record(window) || window.schema !== 'kenn.continuous_window.v1' || window.valid !== true
        || window.input_channels !== 2 || window.correlation_valid !== true
        || !numberIn(window.sequence, 1, Number.MAX_SAFE_INTEGER) || !Number.isInteger(window.sequence)
        || !numberIn(window.source_generation, 1, Number.MAX_SAFE_INTEGER) || !Number.isInteger(window.source_generation)
        || !numberIn(window.start_sample, 0, Number.MAX_SAFE_INTEGER) || !Number.isInteger(window.start_sample)
        || !numberIn(window.end_sample, window.start_sample + 1, Number.MAX_SAFE_INTEGER) || !Number.isInteger(window.end_sample)
        || !numberIn(window.duration_seconds, 0.1 - 1 / value.sample_rate, 0.1 + 1 / value.sample_rate)
        || Math.abs((window.end_sample - window.start_sample) / value.sample_rate - window.duration_seconds) > 1 / value.sample_rate) return // The six stereo points require one coherent 100 ms observation.
  } else if (grade.points_available !== 0 || grade.points !== 0 || value.stereo !== null) {
    return // Unavailable evidence is not a zero-point grade.
  }
  return value as unknown as KennInsertGrade
}
