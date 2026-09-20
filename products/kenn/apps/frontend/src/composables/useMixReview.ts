import { computed, ref, shallowRef } from 'vue'
import { i18n } from '../locales'
import {
  ApiError,
  fetchAuthSession,
  fetchMixReviewReport,
  loginDashboard,
  pollMixReviewUntilDone,
  submitMixReview,
} from '../api'
import type { BandMode, MixReview, MixReviewView } from '../utils/mixReviewTypes'
import { createMockDecodedAudio, createMockMixReview } from '../utils/mixReviewMock'
import { normalizeMixReview } from '../utils/mixReviewNormalize'
import { decodeWavFile, type DecodedAudio } from '../utils/wavDecode'
import { readMixReviewMock } from '../utils/envFlags'
import { refreshSessionCard } from './useKenn'

/** Jack Dashboard 密码（可选）；留空表示当前环境无需登录 */
function readDashboardPasswordFromEnv(): string {
  return String(import.meta.env.VITE_MIX_REVIEW_DASHBOARD_PASSWORD ?? '').trim()
}

export function useMixReview() {
  const mixFile = ref<File | null>(null)
  const referenceFile = ref<File | null>(null)
  const title = ref('')
  const version = ref('')
  const authenticated = ref(false)
  const useMock = ref(readMixReviewMock())

  const status = ref<'idle' | 'uploading' | 'processing' | 'completed' | 'failed'>('idle')
  /** 状态文案的 i18n key（mixReview.*） */
  const statusKey = ref('statusIdle')
  /** 错误文案的 i18n key；有 errorDetail 时优先显示原始信息 */
  const errorKey = ref('')
  /** 接口/异常原文（无 errorKey 时使用） */
  const errorDetail = ref('')
  const review = shallowRef<MixReview | null>(null)
  const decoded = shallowRef<DecodedAudio | null>(null)
  const activeView = ref<MixReviewView>('waveform')
  const bandMode = ref<BandMode>('raw')

  let abort: AbortController | null = null

  const isBusy = computed(
    () => status.value === 'uploading' || status.value === 'processing',
  )
  const metrics = computed(() => review.value?.metrics ?? null)

  function isAbortError(e: unknown) {
    return (
      (e instanceof DOMException && e.name === 'AbortError') ||
      (e instanceof Error && e.name === 'AbortError')
    )
  }

  function wait(ms: number, signal: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException('Aborted', 'AbortError'))
        return
      }
      const timer = window.setTimeout(() => resolve(), ms)
      const onAbort = () => {
        window.clearTimeout(timer)
        reject(new DOMException('Aborted', 'AbortError'))
      }
      signal.addEventListener('abort', onAbort, { once: true })
    })
  }

  function cancelAnalyze() {
    abort?.abort()
    abort = null
    clearError()
    status.value = 'idle'
    statusKey.value = 'statusIdle'
  }

  function clearError() {
    errorKey.value = ''
    errorDetail.value = ''
  }

  function setErrorKey(key: string) {
    errorKey.value = key
    errorDetail.value = ''
  }

  function setErrorDetail(message: string) {
    errorKey.value = ''
    errorDetail.value = message
  }

  async function checkSession() {
    if (useMock.value) {
      authenticated.value = true
      return
    }
    authenticated.value = await fetchAuthSession()
  }

  /** 若 .env 配置了 Dashboard 密码，则静默登录（无 UI） */
  async function ensureAuthFromEnv() {
    if (useMock.value || authenticated.value) return
    const pwd = readDashboardPasswordFromEnv()
    if (!pwd) return
    try {
      await loginDashboard(pwd)
      authenticated.value = true
    } catch (e) {
      authenticated.value = false
      if (e instanceof ApiError && e.message) throw e
      throw new ApiError('Dashboard login failed', 401)
    }
  }

  function setMixFile(file: File | null) {
    mixFile.value = file
    decoded.value = null
    if (file && !title.value) {
      title.value = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ')
    }
  }

  function setReferenceFile(file: File | null) {
    referenceFile.value = file
  }

  async function runMockAnalyze(signal: AbortSignal) {
    status.value = 'uploading'
    statusKey.value = 'statusAnalysing'
    clearError()
    review.value = null
    if (mixFile.value) {
      try {
        decoded.value = await decodeWavFile(mixFile.value)
      } catch {
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
        decoded.value = createMockDecodedAudio()
      }
    } else {
      decoded.value = createMockDecodedAudio()
    }
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    status.value = 'processing'
    statusKey.value = 'statusAnalysing'
    await wait(800, signal)
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const locale = (i18n.global.locale.value === 'zh-CN' ? 'zh-CN' : 'en-US') as
      | 'zh-CN'
      | 'en-US'
    review.value = createMockMixReview(title.value.trim() || undefined, locale)
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    status.value = 'completed'
    statusKey.value = 'statusCompleted'
  }

  async function analyze() {
    clearError()
    abort?.abort()
    abort = new AbortController()
    const { signal } = abort

    if (useMock.value) {
      try {
        await runMockAnalyze(signal)
      } catch (e) {
        if (isAbortError(e)) {
          status.value = 'idle'
          statusKey.value = 'statusIdle'
          return
        }
        status.value = 'failed'
        statusKey.value = 'statusFailed'
        setErrorKey('errMixReviewFailed')
      }
      return
    }

    review.value = null
    if (!mixFile.value) {
      setErrorKey('errChooseWav')
      status.value = 'idle'
      statusKey.value = 'statusIdle'
      return
    }
    // 右侧工程信息：开始分析时拉一次（不改左侧可视流程）
    void refreshSessionCard()
    status.value = 'uploading'
    statusKey.value = 'statusDecoding'
    try {
      decoded.value = await decodeWavFile(mixFile.value)
    } catch {
      decoded.value = null
    }
    if (signal.aborted) {
      status.value = 'idle'
      statusKey.value = 'statusIdle'
      return
    }
    statusKey.value = 'statusUploading'
    try {
      await ensureAuthFromEnv()
    } catch (e) {
      status.value = 'failed'
      statusKey.value = 'statusFailed'
      if (e instanceof ApiError && e.message) setErrorDetail(e.message)
      else setErrorKey('errLoginFailed')
      return
    }
    const form = new FormData()
    // 字段名与 Jack KENN / 后台 Mix Review multipart 一致
    form.append('file', mixFile.value, mixFile.value.name)
    if (referenceFile.value) {
      form.append('reference', referenceFile.value, referenceFile.value.name)
    }
    form.append('title', title.value.trim())
    form.append('version', version.value.trim())
    form.append('mix_goal', 'premaster')
    form.append('reference_id', '')

    try {
      const submitted = await submitMixReview(form)
      if (signal.aborted) {
        status.value = 'idle'
        statusKey.value = 'statusIdle'
        return
      }
      const id = submitted.id || submitted.review?.id
      const immediate = normalizeMixReview(submitted.review || submitted)
      if (immediate.metrics && (submitted.status === 'completed' || submitted.review?.metrics)) {
        review.value = immediate
        status.value = 'completed'
        statusKey.value = 'statusCompleted'
        return
      }
      if (!id) {
        throw new ApiError(submitted.error || 'No review id returned', 500)
      }
      status.value = 'processing'
      statusKey.value = 'statusAnalysing'
      const done = await pollMixReviewUntilDone(id, {
        signal,
        onTick: (tick) => {
          const s = String(tick.status || '').toLowerCase()
          if (s === 'processing') statusKey.value = 'statusAnalysing'
          else if (s === 'pending') statusKey.value = 'statusQueued'
        },
      })
      if (String(done.status).toLowerCase() === 'failed' || done.review?.status === 'failed') {
        status.value = 'failed'
        statusKey.value = 'statusFailed'
        const msg = done.error || done.review?.error
        if (msg) setErrorDetail(msg)
        else setErrorKey('errAnalysisFailed')
        return
      }
      if (signal.aborted) {
        status.value = 'idle'
        statusKey.value = 'statusIdle'
        return
      }

      let normalized = normalizeMixReview(done.review || done)
      // 状态接口偶发缺完整 metrics 时，再拉报告 JSON 兜底
      if (!normalized.metrics?.bands && id) {
        try {
          const report = await fetchMixReviewReport(id)
          normalized = normalizeMixReview(report)
        } catch {
          // 保留轮询得到的状态数据
        }
      }
      if (!normalized.id) normalized.id = id
      review.value = normalized
      status.value = 'completed'
      statusKey.value = 'statusCompleted'
    } catch (e) {
      if (isAbortError(e) || signal.aborted) {
        status.value = 'idle'
        statusKey.value = 'statusIdle'
        return
      }
      status.value = 'failed'
      statusKey.value = 'statusFailed'
      if (e instanceof ApiError && e.status === 401) {
        authenticated.value = false
        setErrorKey('errUnauthorized')
      } else if (e instanceof ApiError && e.message === 'No review id returned') {
        setErrorKey('errNoReviewId')
      } else if (e instanceof Error && e.message) {
        setErrorDetail(e.message)
      } else {
        setErrorKey('errMixReviewFailed')
      }
    }
  }

  return {
    mixFile,
    referenceFile,
    title,
    version,
    authenticated,
    useMock,
    status,
    statusKey,
    errorKey,
    errorDetail,
    review,
    decoded,
    activeView,
    bandMode,
    isBusy,
    metrics,
    checkSession,
    setMixFile,
    setReferenceFile,
    analyze,
    cancelAnalyze,
  }
}
