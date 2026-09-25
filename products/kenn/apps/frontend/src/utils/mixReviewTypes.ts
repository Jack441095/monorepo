/** 对齐 Jack 音频分析 API：指标与 Mix Review 报告结构 */

export type BandKey =
  | 'sub'
  | 'bass'
  | 'low_mids'
  | 'mids'
  | 'presence'
  | 'sibilance'
  | 'air'

export type BandMap = Partial<Record<BandKey, number>>

export const BAND_ORDER: BandKey[] = [
  'sub',
  'bass',
  'low_mids',
  'mids',
  'presence',
  'sibilance',
  'air',
]

export const BAND_LABELS: Record<BandKey, string> = {
  sub: 'SUB',
  bass: 'BASS',
  low_mids: 'LOW MIDS',
  mids: 'MIDS',
  presence: 'PRESENCE',
  sibilance: 'SIBILANCE',
  air: 'AIR',
}

export const BAND_HZ_HINTS: Record<BandKey, string> = {
  sub: '20–60',
  bass: '60–150',
  low_mids: '150–400',
  mids: '400–2k',
  presence: '2–6k',
  sibilance: '6–8k',
  air: '8–16k',
}

/** 均衡混音下各频段能量占比的预期区间（合计约 1） */
export const BAND_EXPECT: Record<BandKey, { min: number; max: number }> = {
  sub: { min: 0.05, max: 0.18 },
  bass: { min: 0.1, max: 0.24 },
  low_mids: { min: 0.1, max: 0.28 },
  mids: { min: 0.14, max: 0.3 },
  presence: { min: 0.08, max: 0.2 },
  sibilance: { min: 0.02, max: 0.1 },
  air: { min: 0.02, max: 0.1 },
}

export type BandStatus = 'ok' | 'warn' | 'bad'

/** 判断频段占比相对预期：正常 / 临界 / 超标 */
export function bandStatus(key: BandKey, value: number, forceBad = false): BandStatus {
  if (forceBad) return 'bad'
  const v = Math.abs(Number(value) || 0)
  const { min, max } = BAND_EXPECT[key]
  if (v >= min && v <= max) return 'ok'
  const slack = Math.max(0.03, (max - min) * 0.35)
  if (v >= min - slack && v <= max + slack) return 'warn'
  return 'bad'
}

export interface MixReviewFlag {
  severity?: string
  label?: string
  detail?: string
  confidence?: string
}

export interface MixReviewAction {
  rank?: number
  priority?: string
  focus?: string
  action?: string
  reason?: string
}

export interface CorrelationTimeline {
  window_seconds?: number
  timestamps?: number[]
  correlation?: number[]
  balance?: number[]
  dip_events?: Array<{
    start_seconds?: number
    end_seconds?: number
    duration_seconds?: number
    min_correlation?: number
  }>
  vectorscope_points?: Array<[number, number]>
}

export interface MixMetrics {
  filename?: string
  duration_seconds?: number
  sample_rate?: number
  channels?: number
  peak_dbfs?: number
  left_peak_dbfs?: number
  right_peak_dbfs?: number
  true_peak_dbfs?: number
  rms_dbfs_estimate?: number
  crest_factor_db?: number
  dynamic_range_estimate_db?: number
  clipping_risk?: boolean
  clipped_frames_estimate?: number
  integrated_lufs?: number | string
  stereo_balance?: number
  stereo_correlation?: number
  stereo_width_ratio?: number
  bands?: BandMap
  perceptual_bands?: BandMap
  log_bands_40?: number[]
  perceptual_summary?: {
    dominant_band?: string
    presence_share?: number
    low_end_share?: number
    description?: string
  }
  correlation_timeline?: CorrelationTimeline
  technical_score?: number
  technical_rating?: string
}

export interface MixComparison {
  band_delta?: BandMap
  perceptual_band_delta?: BandMap
  rms_delta_db?: number
  peak_delta_db?: number
  crest_delta_db?: number
  stereo_width_delta?: number
  correlation_delta?: number
  largest_spectral_difference?: { band?: string; delta?: number }
  match_score?: number
}

export interface MixReviewNextStep {
  kind: 'command' | 'question'
  say: string
  why?: string
}

export interface MixReview {
  id?: string
  title?: string
  status?: string
  version_label?: string
  created_at?: string
  ok?: boolean
  error?: string
  metrics?: MixMetrics
  flags?: MixReviewFlag[]
  summary?: string
  action_plan?: MixReviewAction[]
  advice?: string[]
  disclaimer?: string
  comparison?: MixComparison
  comparison_advice?: string[]
  /** One question or command KENN suggests saying next (backend: core/advice_next_step.py). */
  next_step?: MixReviewNextStep
  reference?: { filename?: string; name?: string; id?: string }
  /** Jack 报告：曲风识别 */
  mix_style?: { name?: string; genre?: string; label?: string; genre_key?: string }
}

export interface MixReviewSubmitResult {
  ok: boolean
  id?: string
  status?: string
  error?: string
  review?: MixReview
}

export interface MixReviewStatusResult {
  ok: boolean
  id?: string
  status?: string
  error?: string | null
  review?: MixReview
}

export interface ReferenceMatchResult {
  status: string
  preset_id?: string
  preset_download_url?: string
  matching?: {
    spectral_bands?: Record<string, { mix_db?: number; ref_db?: number; delta_db?: number }>
    dynamics?: {
      mix_crest_factor_db?: number
      ref_crest_factor_db?: number
      crest_delta_db?: number
      mix_rms_db?: number
      ref_rms_db?: number
      rms_delta_db?: number
    }
    stereo?: {
      mix_correlation?: number
      ref_correlation?: number
      mono_compatible?: boolean
      stereo_balance_advice?: string
    }
    device_recommendations?: Array<{
      device?: string
      role?: string
      summary?: string
      actions?: string[]
    }>
  }
}

export type MixReviewView =
  | 'waveform'
  | 'bands'
  | 'masking'
  | 'racks'
  | 'midi'
  | 'timeline'
  | 'metrics'
  | 'reference'
  | 'classification'
export type BandMode = 'raw' | 'perceptual' | 'log40'
