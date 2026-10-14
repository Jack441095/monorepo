import { describe, expect, it } from 'vitest'
import { normalizeMixReview } from './mixReviewNormalize'

describe('normalizeMixReview next step', () => {
  it('keeps the suggested question so the panel can offer an Ask KENN button', () => {
    const review = normalizeMixReview({
      flags: [],
      next_step: { kind: 'question', say: 'how do I keep my master under -1 dBTP?', why: 'Mix Review measured the whole render.' },
    })
    expect(review.next_step).toEqual({
      kind: 'question',
      say: 'how do I keep my master under -1 dBTP?',
      why: 'Mix Review measured the whole render.',
    })
  })

  it('drops a next step with nothing to say', () => {
    expect(normalizeMixReview({ flags: [], next_step: { kind: 'question', say: '' } }).next_step).toBeUndefined()
    expect(normalizeMixReview({ flags: [] }).next_step).toBeUndefined()
  })
})

describe('normalizeMixReview grade', () => {
  const grade = {
    points: 17.5,
    points_available: 22,
    full_marks: 100,
    meaning: '17.5 of 22 points available, out of a possible 100; not graded: reference match (no reference track supplied).',
    parts: [{ part: 'technical_health', points: 7.5, points_available: 12, full_marks: 30 }],
    ungraded: [{ part: 'reference_match', reason: 'no reference track supplied' }],
  }

  it('passes the backend grade through untouched', () => {
    expect(normalizeMixReview({ flags: [], grade }).grade).toMatchObject({ points: 17.5, points_available: 22 })
  })

  it('does not invent a score when the backend sent no grade', () => {
    // The old fallback turned any flagged review into 50-98 / 100 and a "Solid with checks" label.
    const review = normalizeMixReview({ metrics: { peak_dbfs: -0.5 }, flags: [{ severity: 'high', label: 'Clipping' }] })
    expect(review.grade).toBeUndefined()
    expect(review.metrics).not.toHaveProperty('technical_score')
    expect(review.metrics).not.toHaveProperty('technical_rating')
  })

  it('drops a grade missing its numbers instead of patching it up', () => {
    expect(normalizeMixReview({ flags: [], grade: { meaning: 'x' } }).grade).toBeUndefined()
  })

  it('leaves unmeasured figures out of the fallback summary', () => {
    const summary = normalizeMixReview({ flags: [{ severity: 'low', label: 'Narrow' }] }).summary
    expect(summary).not.toMatch(/-0\.07|-11\.7/)
    expect(summary).toContain('1 area(s)')
  })
})
