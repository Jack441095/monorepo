/**
 * Mix Review 接口：对接 velvet_thunder Dashboard（默认 :8080，/api/admin/*）。
 *
 * 鉴权说明（Jack Dashboard）：
 * - Cookie 会话：所有请求须 credentials: 'include'
 * - CSRF：POST/PUT/PATCH/DELETE 必须带请求头 X-CSRF-Token
 * - csrf_token 来自 GET /api/auth/session 或 POST /api/auth/login 的响应体
 * - 本地开发：API_URL 留空，由 Vite 把 /api 代理到 8080（避免 CORS）
 */

import { getApiBase, ApiError, parseApiErrorMessage } from './client'
import { API_PATHS } from './paths'
import type {
  MixReview,
  MixReviewStatusResult,
  MixReviewSubmitResult,
  ReferenceMatchResult,
} from '../utils/mixReviewTypes'

/** 内存中的 CSRF；页面刷新后需再调 fetchAuthSession 拿一次 */
let csrfToken = ''

async function parseJson(res: Response): Promise<Record<string, unknown>> {
  return (await res.json().catch(() => ({}))) as Record<string, unknown>
}

/** 从 session/login 响应写入 csrfToken */
function rememberCsrf(data: Record<string, unknown>) {
  const token = String(data.csrf_token ?? '').trim()
  if (token) csrfToken = token
}

/** 合并业务头 + X-CSRF-Token（有 token 才加）；KENN POST 也可复用 */
export function withCsrf(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {}
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  if (extra) {
    if (extra instanceof Headers) {
      extra.forEach((v, k) => {
        headers[k] = v
      })
    } else if (Array.isArray(extra)) {
      for (const [k, v] of extra) headers[k] = v
    } else {
      Object.assign(headers, extra)
    }
  }
  return headers
}

/** Dashboard 密码登录；成功后写入 csrf_token。密码可配在 VITE_MIX_REVIEW_DASHBOARD_PASSWORD */
export async function loginDashboard(password: string): Promise<void> {
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.auth.login}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ password }),
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  rememberCsrf(data)
}

/**
 * 探测会话；dev 模式下后端可自动发 cookie。
 * 必须先调用一次，才能拿到 csrf_token，否则后续 POST 会 403。
 */
export async function fetchAuthSession(): Promise<boolean> {
  const base = getApiBase()
  try {
    const res = await fetch(`${base}${API_PATHS.auth.session}`, { credentials: 'include' })
    if (!res.ok) return false
    const data = await parseJson(res)
    rememberCsrf(data)
    return Boolean(data.authenticated)
  } catch {
    return false
  }
}

/** 已有 csrf 则跳过；避免 KENN 轮询每次都打 /api/auth/session */
export async function ensureAuthSession(): Promise<boolean> {
  if (csrfToken) return true
  return fetchAuthSession()
}

/**
 * 提交混音分析（multipart）。
 * 字段：file、reference?、title、version、mix_goal、reference_id
 * 勿手动设 Content-Type，由浏览器带 multipart boundary。
 */
export async function submitMixReview(form: FormData): Promise<MixReviewSubmitResult> {
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.mixReview.submit()}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf(),
    body: form,
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  return data as unknown as MixReviewSubmitResult
}

/** 轮询单次状态：GET，不需要 CSRF */
export async function fetchMixReviewStatus(id: string): Promise<MixReviewStatusResult> {
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.mixReview.status(id)}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  return data as unknown as MixReviewStatusResult
}

/** 拉取完整报告 JSON（状态结果缺 metrics 时兜底） */
export async function fetchMixReviewReport(id: string): Promise<MixReview> {
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.mixReview.reportJson(id)}`, {
    credentials: 'include',
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  return (data.review || data) as MixReview
}

/**
 * 直到 completed / failed，或已有 metrics 且非 pending/processing。
 * 默认间隔 1.2s，超时 10 分钟。
 */
export async function pollMixReviewUntilDone(
  id: string,
  options?: {
    intervalMs?: number
    timeoutMs?: number
    onTick?: (status: MixReviewStatusResult) => void
    signal?: AbortSignal
  },
): Promise<MixReviewStatusResult> {
  const intervalMs = options?.intervalMs ?? 1200
  const timeoutMs = options?.timeoutMs ?? 10 * 60 * 1000
  const started = Date.now()

  while (Date.now() - started < timeoutMs) {
    if (options?.signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }
    const status = await fetchMixReviewStatus(id)
    options?.onTick?.(status)
    const state = String(status.status || status.review?.status || '').toLowerCase()
    if (state === 'completed' || state === 'failed') return status
    if (status.review?.metrics && state !== 'pending' && state !== 'processing') {
      return status
    }
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => resolve(), intervalMs)
      const onAbort = () => {
        window.clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      }
      if (options?.signal) {
        if (options.signal.aborted) {
          window.clearTimeout(timer)
          reject(new DOMException('Aborted', 'AbortError'))
          return
        }
        options.signal.addEventListener('abort', onAbort, { once: true })
      }
    })
  }
  throw new ApiError('Mix review timed out', 408)
}

/**
 * 提交参考对比与均衡匹配（multipart: mix + reference）。
 */
export async function submitReferenceMatch(
  form: FormData,
  options?: { signal?: AbortSignal },
): Promise<ReferenceMatchResult> {
  const base = getApiBase()
  const res = await fetch(`${base}${API_PATHS.mixReview.referenceMatch()}`, {
    method: 'POST',
    credentials: 'include',
    headers: withCsrf(),
    body: form,
    signal: options?.signal,
  })
  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }
  return data as unknown as ReferenceMatchResult
}
