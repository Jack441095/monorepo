import { describe, expect, it } from 'vitest'

import {
  filterSloClassifications,
  normalizeSloClassificationItem,
  normalizeSloClassificationResponse,
} from './sloClassification'
import { createSloMockResponse } from '../mocks/sloClassifications'

describe('SLO classification contract', () => {
  it('clamps confidence and normalizes missing fields', () => {
    const item = normalizeSloClassificationItem({ confidence: 7, primary_label: 'Kick' })
    expect(item.confidence).toBe(1)
    expect(item.displayName).toBe('Unnamed sample')
    expect(item.tags).toEqual([])
  })

  it('keeps OOD results neutral', () => {
    const response = createSloMockResponse()
    const ood = response.items.find((item) => item.evidenceSource === 'OOD abstention')
    expect(ood?.primaryLabel).toBe('Needs review')
    expect(ood?.reviewRequired).toBe(true)
  })

  it('rejects malformed envelopes', () => {
    expect(() => normalizeSloClassificationResponse({ status: 'ready', items: [] })).toThrow()
  })

  it('filters by text, category, and review state', () => {
    const items = createSloMockResponse().items
    expect(filterSloClassifications(items, 'punchy', 'Drums', false)).toHaveLength(1)
    expect(filterSloClassifications(items, '', '', true).every((item) => item.reviewRequired)).toBe(true)
  })

  it('uses the same normalized response type in mock mode', () => {
    const mock = createSloMockResponse()
    expect(mock.schema).toBe('kenn.slo-classifications/v1')
    expect(mock.status).toBe('ready')
  })
})
