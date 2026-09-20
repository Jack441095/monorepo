/** Jack / KENN 接口路径；改 URL 只动本文件。前缀见 VITE_MIX_REVIEW_API_PREFIX，基址见 API_URL。 */

export function mixReviewPrefix(): string {
  const raw = String(import.meta.env.VITE_MIX_REVIEW_API_PREFIX ?? '/api').trim()
  return raw.replace(/\/$/, '') || '/api'
}

export const API_PATHS = {
  auth: {
    login: '/api/auth/login',
    session: '/api/auth/session',
  },

  /** Mix Review：multipart 提交 / 轮询 / 报告 JSON */
  mixReview: {
    submit: () => `${mixReviewPrefix()}/mix-review`,
    status: (id: string) =>
      `${mixReviewPrefix()}/mix-review-status?id=${encodeURIComponent(id)}`,
    reportJson: (id: string) =>
      `${mixReviewPrefix()}/mix-review-report/${encodeURIComponent(id)}.json`,
    referenceMatch: () => `${mixReviewPrefix()}/mix-review/reference-match`,
    referencePreset: (id: string) =>
      `${mixReviewPrefix()}/mix-review/reference-preset/${encodeURIComponent(id)}.adv`,
  },

  /** KENN（经 Dashboard /kenn 代理）：问答 / Ableton 会话卡片 */
  /** KENN（经 Dashboard /kenn 代理）：问答 / Ableton 会话卡片 / DAW 命令控制 */
  kenn: {
    ask: '/kenn/api/ask',
    sessionCard: '/kenn/api/ableton/session-card',
    command: '/kenn/api/ableton/command',
    undo: '/kenn/api/ableton/osc/undo',
    parameters: '/kenn/api/plugin/parameters',
    racks: '/kenn/api/racks',
    synthesizeRack: '/kenn/api/racks/synthesize',
    worldModel: '/kenn/api/session/world_model',
    doctorAudit: '/kenn/api/session/doctor/audit',
    doctorRemediate: '/kenn/api/session/doctor/remediate',
    detectScale: '/kenn/api/midi/detect_scale',
    midiGroove: '/kenn/api/midi/groove',
    midiBassline: '/kenn/api/midi/bassline',
    genreCurves: '/kenn/api/genre_curves',
    sloClassifications: '/kenn/api/slo/classifications',
  },
} as const
