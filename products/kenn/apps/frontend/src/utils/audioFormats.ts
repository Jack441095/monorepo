/** 与 Jack velvet_thunder Mix Review 上传格式对齐 */

export const MIX_REVIEW_AUDIO_EXTENSIONS = [
  '.wav',
  '.wave',
  '.mp3',
  '.flac',
  '.aif',
  '.aiff',
  '.m4a',
] as const

/** `<input accept>` 用 */
export const MIX_REVIEW_AUDIO_ACCEPT = [
  ...MIX_REVIEW_AUDIO_EXTENSIONS,
  'audio/wav',
  'audio/x-wav',
  'audio/wave',
  'audio/mpeg',
  'audio/mp3',
  'audio/flac',
  'audio/aiff',
  'audio/x-aiff',
  'audio/mp4',
  'audio/x-m4a',
  'audio/aac',
].join(',')

const EXT_SET = new Set<string>(MIX_REVIEW_AUDIO_EXTENSIONS)

const MIME_PREFIXES = ['audio/'] as const

/** 按扩展名 + MIME 判断是否为可上传的混音/参考轨 */
export function isLikelyMixAudio(file: File): boolean {
  const name = file.name.toLowerCase()
  const type = (file.type || '').toLowerCase()
  const dot = name.lastIndexOf('.')
  const ext = dot >= 0 ? name.slice(dot) : ''
  if (ext && EXT_SET.has(ext)) return true
  if (MIME_PREFIXES.some((p) => type.startsWith(p))) {
    // 浏览器有时只给 audio/*；扩展名已排除时仍放行常见 MIME
    return (
      type.includes('wav') ||
      type.includes('mpeg') ||
      type.includes('mp3') ||
      type.includes('flac') ||
      type.includes('aiff') ||
      type.includes('mp4') ||
      type.includes('m4a') ||
      type.includes('aac')
    )
  }
  return false
}
