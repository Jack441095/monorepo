import type { MixReview } from './mixReviewTypes'
import type { DecodedAudio } from './wavDecode'

type LocaleCode = 'zh-CN' | 'en-US'

function bandSet(seed: number) {
  // 故意拉偏，方便演示绿/橙/红；seed 不同时占比要明显可辨
  const raw =
    seed === 0
      ? [
          0.12, // 超低 — 正常
          0.2, // 低频 — 正常
          0.32, // 低中频 — 偏高
          0.22, // 中频 — 正常
          0.14, // 临场感 — 正常
          0.14, // 齿音 — 偏高
          0.03, // 空气感 — 偏低
        ]
      : [
          0.08, // 超低 — 偏低
          0.16, // 低频
          0.22, // 低中频
          0.28, // 中频 — 感知更重
          0.18, // 临场感 — 偏高
          0.1, // 齿音
          0.06, // 空气感
        ]
  const sum = raw.reduce((a, b) => a + b, 0)
  const keys = ['sub', 'bass', 'low_mids', 'mids', 'presence', 'sibilance', 'air'] as const
  const out: Record<string, number> = {}
  keys.forEach((k, i) => {
    out[k] = Number((raw[i]! / sum).toFixed(4))
  })
  return out
}

const MOCK_COPY = {
  'zh-CN': {
    defaultTitle: '午夜混音',
    summary:
      '整体扎实，需留意（82/100）。中频清晰；注意临场感/齿音附近的能量堆积。此为 UI 测试用模拟数据。',
    perceptualDescription: '感知焦点集中在中频（模拟）。',
    rating: '扎实，需检查',
    flags: [
      {
        severity: 'high' as const,
        label: '齿音峰值',
        detail: '临场感/齿音频段能量相对偏高。',
      },
      {
        severity: 'medium' as const,
        label: '低频堆积',
        detail: '低中频/低频占比偏强，建议在小音箱上检查听感。',
      },
    ],
    advice: [
      '在 6–8 kHz 附近使用动态均衡抑制人声齿音。',
      '检查低频/超低频的单声道兼容性。',
    ],
    actionFocus: '齿音峰值',
    action: '用动态均衡或去齿音器压低刺耳临场感。',
    actionReason: '模拟操作建议，用于 UI 展示。',
    mixFilename: '混音终稿_主轨.wav',
    referenceFilename: '参考轨.wav',
    referenceName: '参考轨',
    disclaimer: '模拟 Mix Review 数据 — 非 Jack 真实分析。',
  },
  'en-US': {
    defaultTitle: 'Midnight Session',
    summary:
      'Solid with checks (82/100). Mid-range is clear; watch energy build-up around presence/sibilance. Mock data for UI testing.',
    perceptualDescription: 'Perceived focus around mids (mock).',
    rating: 'Solid with checks',
    flags: [
      {
        severity: 'high' as const,
        label: 'Sibilance Peak',
        detail: 'Presence/sibilance energy is elevated relative to the rest of the spectrum.',
      },
      {
        severity: 'medium' as const,
        label: 'Low End Build-up',
        detail: 'Low mids / bass share is strong — check translation on small speakers.',
      },
    ],
    advice: [
      'Apply dynamic EQ around 6–8 kHz to tame vocal sibilance.',
      'Check mono-compatibility of the low-end sub frequencies.',
    ],
    actionFocus: 'Sibilance Peak',
    action: 'Tame harsh presence with dynamic EQ or de-esser.',
    actionReason: 'Mock action for UI.',
    mixFilename: 'Mix_Final_Main.wav',
    referenceFilename: 'Reference_Track.wav',
    referenceName: 'Reference',
    disclaimer: 'Mock Mix Review payload — not from Jack analysis.',
  },
} as const

export function createMockMixReview(title?: string, locale: LocaleCode = 'en-US'): MixReview {
  const copy = MOCK_COPY[locale] ?? MOCK_COPY['en-US']
  const n = 120
  const timestamps: number[] = []
  const correlation: number[] = []
  const balance: number[] = []
  const vectorscope_points: Array<[number, number]> = []
  for (let i = 0; i < n; i += 1) {
    timestamps.push(Number((i * 0.1).toFixed(2)))
    correlation.push(Number((0.75 + 0.2 * Math.sin(i / 9)).toFixed(3)))
    balance.push(Number((0.08 * Math.sin(i / 7)).toFixed(3)))
    const a = (i / n) * Math.PI * 4
    vectorscope_points.push([
      Number((0.55 * Math.sin(a) + 0.12 * Math.sin(a * 3)).toFixed(3)),
      Number((0.62 * Math.cos(a * 0.9) + 0.1 * Math.cos(a * 2.2)).toFixed(3)),
    ])
  }

  const log_bands_40 = Array.from({ length: 40 }, (_, i) => {
    const x = i / 39
    return 0.01 + 0.04 * Math.exp(-((x - 0.35) ** 2) / 0.08) + 0.015 * Math.sin(i)
  })
  const logSum = log_bands_40.reduce((a, b) => a + b, 0)

  return {
    id: 'mock-demo',
    title: title?.trim() || copy.defaultTitle,
    status: 'completed',
    version_label: 'v2',
    created_at: new Date().toISOString(),
    ok: true,
    summary: copy.summary,
    metrics: {
      filename: copy.mixFilename,
      duration_seconds: 184,
      sample_rate: 44100,
      channels: 2,
      peak_dbfs: -1.2,
      true_peak_dbfs: -0.8,
      rms_dbfs_estimate: -12.4,
      crest_factor_db: 11.2,
      clipping_risk: false,
      integrated_lufs: -11.2,
      stereo_correlation: 0.86,
      stereo_width_ratio: 0.42,
      bands: bandSet(0),
      perceptual_bands: bandSet(1),
      log_bands_40: log_bands_40.map((v) => Number((v / logSum).toFixed(4))),
      perceptual_summary: {
        dominant_band: 'mids',
        presence_share: 0.24,
        low_end_share: 0.32,
        description: copy.perceptualDescription,
      },
      correlation_timeline: {
        window_seconds: 0.1,
        timestamps,
        correlation,
        balance,
        dip_events: [
          { start_seconds: 4.2, end_seconds: 4.6, duration_seconds: 0.4, min_correlation: 0.12 },
        ],
        vectorscope_points,
      },
      technical_score: 82,
      technical_rating: copy.rating,
    },
    flags: copy.flags.map((f) => ({ ...f })),
    advice: [...copy.advice],
    action_plan: [
      {
        rank: 1,
        priority: 'high',
        focus: copy.actionFocus,
        action: copy.action,
        reason: copy.actionReason,
      },
    ],
    comparison: {
      rms_delta_db: 1.4,
      crest_delta_db: -0.8,
      band_delta: {
        sub: 0.02,
        bass: 0.03,
        low_mids: -0.01,
        mids: -0.02,
        presence: 0.04,
        sibilance: 0.05,
        air: -0.01,
      },
      largest_spectral_difference: { band: 'sibilance', delta: 0.05 },
    },
    reference: { filename: copy.referenceFilename, name: copy.referenceName },
    disclaimer: copy.disclaimer,
  }
}

function mockNoise(i: number, seed: number) {
  const x = Math.sin(i * 127.1 + seed * 311.7) * 43758.5453
  return x - Math.floor(x)
}

export function createMockDecodedAudio(): DecodedAudio {
  // 密实等高波形（不做淡入淡出橄榄球包络）
  const peaks = new Float32Array(2800)
  for (let i = 0; i < peaks.length; i += 1) {
    const n1 = mockNoise(i, 1)
    const n2 = mockNoise(i, 2)
    const n3 = mockNoise(i * 2, 3)
    const n4 = mockNoise(i * 5, 4)
    // 主体电平 + 局部抖动 + 偶发冲击
    const body = 0.72 + 0.22 * n1
    const grain = 0.08 * n2 + 0.06 * n3
    const hit = n4 > 0.88 ? 0.12 * n2 : 0
    // 首尾略收一点（真实文件也很少两端贴满）
    const edge = i < 8 || i > peaks.length - 9 ? 0.85 : 1
    peaks[i] = Math.min(1, (body + grain + hit) * edge)
  }
  return {
    sampleRate: 44100,
    channels: 2,
    duration: 12,
    peaks,
    channelData: [],
  }
}
