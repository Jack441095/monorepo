import { describe, expect, it } from 'vitest'
import { ApiError, userFacingKennError } from './client'

describe('userFacingKennError', () => {
  const fallback = "KENN couldn't complete that request safely. Nothing changed; try again."

  it('keeps bounded human-readable API guidance', () => {
    expect(userFacingKennError(
      new ApiError("Ableton Live isn't responding — check the connection and try again."),
      fallback,
    )).toBe("Ableton Live isn't responding — check the connection and try again.")
  })

  it('never exposes stack traces or raw implementation errors', () => {
    expect(userFacingKennError(
      new ApiError('TypeError: boom at handleCommand (/srv/server.ts:42:9)'),
      fallback,
    )).toBe(fallback)
    expect(userFacingKennError(new Error('private implementation detail'), fallback)).toBe(fallback)
  })

  it('turns browser transport failures into actionable local guidance', () => {
    expect(userFacingKennError(new TypeError('Failed to fetch'), fallback)).toBe(
      'KENN is offline — check the local server and try again. Nothing changed.',
    )
  })

  it('bounds unexpectedly long server messages', () => {
    expect(userFacingKennError(new ApiError('x'.repeat(321)), fallback)).toBe(fallback)
  })
})
