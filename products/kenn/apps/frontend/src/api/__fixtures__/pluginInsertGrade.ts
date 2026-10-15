import type { KennInsertGrade } from '../pluginInsertGrade'

/** Fresh generated stereo evidence, independent of any Live session or process-wide report. */
export function insertGrade(owner = 'native-owner', insert = 'kick-insert', host = 'Kick'): KennInsertGrade {
  return {
    schema: 'kenn.plugin_insert_grade.v1', scope: 'selected_insert_window', conversation_id: owner,
    insert_id: insert, host_track_name: host, sample_rate: 48000,
    measurement_window: { schema: 'kenn.continuous_window.v1', valid: true, sequence: 10, source_generation: 1,
      input_channels: 2, correlation_valid: true,
      start_sample: 43200, end_sample: 48000, duration_seconds: 0.1, dropped_samples: 0, invalid_samples: 0 },
    freshness: { age_seconds: 0.1, max_age_seconds: 1, current_for_diagnosis: true },
    status: 'graded', reason: 'Only stereo correlation is scored for this insert window.',
    grade: { points: 5.1, points_available: 6, full_marks: 100, meaning: '5.1 of 6 points available, out of a possible 100.',
      parts: [{ part: 'technical_health', points: 5.1, points_available: 6, full_marks: 30, left_out: [], note: 'Stereo only.' }],
      ungraded: [{ part: 'declared_target', reason: 'LUFS and true peak are unavailable.' },
        { part: 'reference_match', reason: 'No associated reference comparison.' }] },
    stereo: { points: 5.1, points_available: 6, points_lost: 0.9, source: 'House correlation rule',
      tier: 'judgement', threshold_band: '[0.25, 0.5)', correlation: 0.3 },
    unscored_dimensions: [{ dimension: 'dynamic_health', reason: 'No qualified LUFS or true-peak evidence.' }],
  }
}

export function ungradedInsert(): KennInsertGrade {
  const grading = insertGrade()
  return { ...grading, status: 'ungraded', reason: 'No valid stereo channel layout.', stereo: null,
    grade: { ...grading.grade, points: 0, points_available: 0, parts: [], meaning: 'No points are available; this insert is not graded.',
      ungraded: [{ part: 'technical_health', reason: 'No valid stereo channel layout.' }, ...grading.grade.ungraded] } }
}
