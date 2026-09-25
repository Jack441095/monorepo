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
