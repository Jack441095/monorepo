import { describe, expect, it } from 'vitest'
import { insertGrade, ungradedInsert } from './__fixtures__/pluginInsertGrade'
import { parsePluginInsertGrade } from './pluginInsertGrade'

const parse = (value: unknown) => parsePluginInsertGrade(value, 'native-owner', 'kick-insert', 'Kick')

describe('selected insert partial grade contract', () => {
  it('retains six available stereo points and the full 100-point denominator without rescaling', () => {
    const result = parse(insertGrade())!
    expect(result.grade).toMatchObject({ points: 5.1, points_available: 6, full_marks: 100 })
    expect(result.grade.ungraded.map(part => part.part)).toEqual(['declared_target', 'reference_match'])
    expect(parse(ungradedInsert())).toMatchObject({ status: 'ungraded', stereo: null, grade: { points_available: 0 } })
  })

  it.each([
    ['conversation_id', 'another-owner'], ['insert_id', 'bass-insert'], ['host_track_name', 'Bass'],
    ['scope', 'master'], ['schema', 'unknown'], ['sample_rate', Infinity], ['sample_rate', true],
  ])('withholds an unrelated or malformed %s', (key, value) => {
    expect(parse({ ...insertGrade(), [key]: value })).toBeUndefined()
  })

  it.each([NaN, Infinity, true, -0.1, 6.1])('rejects invalid points %s instead of repairing them', points => {
    const grading = insertGrade()
    expect(parse({ ...grading, grade: { ...grading.grade, points } })).toBeUndefined()
  })

  it('rejects rescaled scores, mismatched totals, duplicate parts and an unqualified measurement window', () => {
    const grading = insertGrade()
    expect(parse({ ...grading, grade: { ...grading.grade, points: 85, points_available: 100 } })).toBeUndefined()
    expect(parse({ ...grading, stereo: { ...grading.stereo, points: 6 } })).toBeUndefined()
    expect(parse({ ...grading, grade: { ...grading.grade, ungraded: [grading.grade.ungraded[0], grading.grade.ungraded[0]] } })).toBeUndefined()
    expect(parse({ ...grading, measurement_window: { ...grading.measurement_window, valid: false } })).toBeUndefined()
    expect(parse({ ...grading, measurement_window: { ...grading.measurement_window, input_channels: 1 } })).toBeUndefined()
    expect(parse({ ...grading, measurement_window: { ...grading.measurement_window, correlation_valid: false } })).toBeUndefined()
    expect(parse({ ...grading, measurement_window: { ...grading.measurement_window, end_sample: 96000 } })).toBeUndefined()
    expect(parse({ ...grading, freshness: { ...grading.freshness, age_seconds: 1.1 } })).toBeUndefined()
    expect(parse({ ...grading, unscored_dimensions: [{ dimension: 'dynamic_health', reason: {} }] })).toBeUndefined()
  })

  it('does not accept a score hidden behind an ungraded label', () => {
    expect(parse({ ...insertGrade(), status: 'ungraded' })).toBeUndefined()
  })
})
