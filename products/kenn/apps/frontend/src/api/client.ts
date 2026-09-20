/** API 客户端：统一 JSON 请求与错误处理 */

export const getApiBase = () => (typeof API_URL === 'string' ? API_URL.replace(/\/$/, '') : '')

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 500) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

/** 兼容后端 error / FastAPI detail 字段 */
export function parseApiErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback
  const obj = data as Record<string, unknown>
  if (typeof obj.error === 'string') return obj.error
  if (typeof obj.detail === 'string') return obj.detail
  if (Array.isArray(obj.detail)) {
    return obj.detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return String(item)
      })
      .join('; ')
  }
  return fallback
}

/** 统一 JSON 请求封装 */
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase()
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new ApiError(parseApiErrorMessage(data, res.statusText), res.status)
  }

  return data as T
}
