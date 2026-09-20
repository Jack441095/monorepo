import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  message: string
  type: ToastType
}

const toasts = ref<ToastItem[]>([])
let seq = 0

/** 全局轻提示；durationMs <= 0 表示不自动关闭 */
export function showToast(
  message: string,
  type: ToastType = 'info',
  durationMs = 2400,
) {
  const id = ++seq
  toasts.value = [...toasts.value, { id, message, type }]
  if (durationMs > 0) {
    window.setTimeout(() => dismissToast(id), durationMs)
  }
  return id
}

export function dismissToast(id: number) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export function useToastState() {
  return { toasts, dismissToast, showToast }
}
