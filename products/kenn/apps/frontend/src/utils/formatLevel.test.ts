import { describe, expect, it } from 'vitest'
import { formatDb } from './formatLevel'

describe('formatDb', () => {
  it('shows a fader level the way Live does', () => {
    expect(formatDb(-14)).toBe('-14.0 dB')
    expect(formatDb(-16.04)).toBe('-16.0 dB')
    expect(formatDb('-inf')).toBe('-inf dB')
  })

  it('leaves anything else to the raw value', () => {
    expect(formatDb(null)).toBeNull()
    expect(formatDb(undefined)).toBeNull()
    expect(formatDb('0.5')).toBeNull()
  })
})
