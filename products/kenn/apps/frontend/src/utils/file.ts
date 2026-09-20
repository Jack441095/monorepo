export interface UploadFileItem {
  id: string
  file: File
}

export interface AddFilesOptions {
  /** 允许的类型，如 ['png', 'jpg'] 或 '.png,.jpg'；不传则不校验格式 */
  accept?: string | string[]
  /** 单文件大小上限（字节）；不传则不校验大小 */
  maxSize?: number
  typeError?: string
  sizeError?: string
}

export const buildAcceptInput = (accept?: string | string[]): string => {
  if (!accept) return ''
  if (typeof accept === 'string') return accept
  return accept.map((ext) => (ext.startsWith('.') ? ext : `.${ext}`)).join(',')
}

export const isAcceptedFile = (file: File, accept?: string | string[]): boolean => {
  if (!accept || (Array.isArray(accept) && !accept.length)) return true

  const extensions = (Array.isArray(accept) ? accept : accept.split(','))
    .map((item) => item.trim().replace(/^\./, '').toLowerCase())
    .filter(Boolean)

  if (!extensions.length) return true

  const ext = file.name.split('.').pop()?.toLowerCase()
  return ext ? extensions.includes(ext) : false
}
