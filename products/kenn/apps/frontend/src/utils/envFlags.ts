/** 与 Mix Review / KENN 共用的环境开关 */

export function readMixReviewMock(): boolean {
  const raw = String(import.meta.env.VITE_MIX_REVIEW_MOCK ?? '').trim().toLowerCase()
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on'
}
