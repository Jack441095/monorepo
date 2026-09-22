import { describe, expect, it } from 'vitest'
import { parseAdviceFindings } from './kenn'

describe('parseAdviceFindings', () => {
  it('normalizes measured audio findings with listening tests', () => {
    const findings = parseAdviceFindings({
      tool_result: {
        findings: [{
          type: 'possible_masking_candidate',
          severity: 'informational',
          confidence: 0.45,
          explanation: 'Two measured peaks are close enough to check.',
          suggested_listening_test: 'Mute and solo the sources at matched level.',
        }],
      },
    })

    expect(findings).toEqual([{
      title: 'possible masking candidate',
      severity: 'info',
      confidence: 0.45,
      detail: 'Two measured peaks are close enough to check.',
      listeningTest: 'Mute and solo the sources at matched level.',
    }])
  })

  it('extracts bounded realtime review advisories and normalizes severity', () => {
    const findings = parseAdviceFindings({
      orchestration: {
        report: {
          mixing_doctor: {
            alerts: [{ title: 'Headroom', severity: 'warning', message: 'Meter is near the ceiling.', fix_action: 'Check with a true-peak meter.' }],
          },
          project_health: {
            recommendations: [{ title: 'Solo state', severity: 'critical', confidence: 95, description: 'A track remains soloed.', suggestedAction: 'Audition the full mix.' }],
          },
        },
      },
    })

    expect(findings).toHaveLength(2)
    expect(findings[0]).toMatchObject({ severity: 'warning', listeningTest: 'Check with a true-peak meter.' })
    expect(findings[1]).toMatchObject({ severity: 'critical', confidence: 0.95 })
  })

  it('omits unsupported payload data instead of rendering raw JSON', () => {
    expect(parseAdviceFindings({ orchestration: { debug: { findings: [{ error: 'secret' }] } } })).toEqual([])
  })
})
