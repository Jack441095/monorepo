/**
 * API 层入口：路径 + 客户端 + Mix Review 请求。
 *
 * 对接说明（要接哪些接口、改路径改哪）：见同目录 `Jack对接说明.md`
 *
 * 推荐从 `../api` 统一导入：
 *   import { API_PATHS, submitMixReview } from '../api'
 */

export { API_PATHS, mixReviewPrefix } from './paths'
export { getApiBase, ApiError, parseApiErrorMessage, requestJson } from './client'
export {
  loginDashboard,
  fetchAuthSession,
  withCsrf,
  submitMixReview,
  fetchMixReviewStatus,
  fetchMixReviewReport,
  pollMixReviewUntilDone,
} from './mixReview'
export { askKenn, fetchKennSessionCard } from './kenn'
export type { KennAskResult, KennSessionCard, KennSessionTrack, KennSource } from './kenn'
