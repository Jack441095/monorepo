import {
  SLO_CLASSIFICATION_SCHEMA,
  normalizeSloClassificationResponse,
  type SloClassificationResponse,
} from '../api/sloClassification'

const fixtureItems = [
  ['kick-tight-01', 'kick_tight_01.wav', 'Drums', 'Kick', ['Punchy', 'Short'], 0.94, 'Kick', false, null, 'audio model', 'DSP', 6, 5, false, 'ready'],
  ['snare-room-02', 'snare_room_02.wav', 'Drums', 'Snare', ['Acoustic', 'Roomy'], 0.82, 'Snare', false, null, 'audio model', 'DSP', 6, 5, false, 'ready'],
  ['hat-open-03', 'hat_open_03.wav', 'Drums', 'Hi-Hat', ['Open', 'Bright'], 0.71, 'Hi-Hat', false, 'mixed evidence', 'audio-only', 'DSP', 6, 5, false, 'ready'],
  ['bass-sub-04', 'bass_sub_c.wav', 'Bass', 'Bass One-Shot', ['Sub', 'One-Shot'], 0.89, 'Bass One-Shot', false, null, 'audio model', 'DSP', 6, 5, false, 'ready'],
  ['vocal-hook-05', 'vocal_hook_120.wav', 'Vocals', 'Vocal Phrase', ['Loop', 'Female'], 0.63, 'Vocal Phrase', false, null, 'user override', 'USER_OVERRIDE', 6, 4, true, 'ready'],
  ['fx-riser-06', 'fx_riser_8bar.wav', 'FX', 'Riser', ['Transition', 'Loop'], 0.58, 'Riser', false, 'mixed evidence', 'filename heuristic', 'FILENAME', 6, 5, false, 'ready'],
  ['perc-wood-07', 'perc_wood_07.wav', 'Drums', 'Percussion', ['Organic', 'One-Shot'], 0.47, 'Percussion', true, 'weak evidence agreement', 'audio-only', 'DSP', 6, 5, false, 'ready'],
  ['ood-08', 'texture_unknown_08.wav', '', '', ['Texture'], 0.22, 'Needs review', true, 'outside the known audio domain', 'OOD abstention', 'DSP', 6, 5, false, 'ready'],
  ['missing-09', 'new_recording_09.wav', '', '', [], 0, 'Unclassified', true, 'not analysed', 'not run', 'UNKNOWN', 0, 0, false, 'missing'],
  ['stale-10', 'clap_layer_10.wav', 'Drums', 'Clap', ['Layer'], 0.79, 'Clap', true, 'classification requires refresh', 'audio model', 'DSP', 5, 4, false, 'stale'],
  ['synth-11', 'synth_chord_am.wav', 'Synth', 'Chord', ['A Minor', 'One-Shot'], 0.86, 'Chord', false, null, 'metadata-assisted', 'EMBEDDED_METADATA', 6, 5, false, 'ready'],
  ['loop-12', 'break_amen_174.wav', 'Loops', 'Drum Loop', ['174 BPM', 'Break'], 0.76, 'Drum Loop', false, null, 'folder heuristic', 'FOLDER', 6, 5, false, 'ready'],
] as const

export function createSloMockResponse(): SloClassificationResponse {
  return normalizeSloClassificationResponse({
    schema: SLO_CLASSIFICATION_SCHEMA,
    status: 'ready',
    items: fixtureItems.map((item) => ({
      id: item[0], display_name: item[1], category: item[2], subcategory: item[3], tags: [...item[4]],
      confidence: item[5], primary_label: item[6], review_required: item[7], uncertainty_reason: item[8],
      evidence_source: item[9], winning_evidence: item[10], model_version: item[11], taxonomy_version: item[12],
      user_overridden: item[13], classification_state: item[14],
    })),
    summary: { total: fixtureItems.length, returned: fixtureItems.length, needs_review: 4, stale: 1 },
  })
}

export async function fetchSloMockScenario(): Promise<SloClassificationResponse> {
  const scenario = String(import.meta.env.VITE_SLO_CLASSIFICATION_MOCK_SCENARIO ?? 'ready').trim().toLowerCase()
  await new Promise((resolve) => window.setTimeout(resolve, 180))
  if (scenario === 'offline') throw new TypeError('Mock network offline')
  if (scenario === 'error') throw new Error('Mock classification service error')
  if (scenario === 'malformed') return normalizeSloClassificationResponse({ broken: true })
  if (scenario === 'empty') {
    return normalizeSloClassificationResponse({
      schema: SLO_CLASSIFICATION_SCHEMA, status: 'ready', items: [],
      summary: { total: 0, returned: 0, needs_review: 0, stale: 0 },
    })
  }
  return createSloMockResponse()
}
