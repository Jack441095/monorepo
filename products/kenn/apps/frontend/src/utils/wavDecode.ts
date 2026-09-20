/**
 * 浏览器端解码音频画波形（Jack 接口不返回 PCM）。
 * 使用 Web Audio decodeAudioData，常见格式：WAV / MP3 / FLAC / AIFF / M4A（视浏览器而定）。
 */

export interface DecodedAudio {
  sampleRate: number
  channels: number
  duration: number
  peaks: Float32Array
  channelData: Float32Array[]
}

let sharedCtx: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedCtx) sharedCtx = new AudioContext()
  return sharedCtx
}

/** @deprecated 名称保留兼容；实际可解多种格式，等价于 decodeAudioFile */
export async function decodeWavFile(file: File, peakBuckets = 2800): Promise<DecodedAudio> {
  return decodeAudioFile(file, peakBuckets)
}

export async function decodeAudioFile(file: File, peakBuckets = 2800): Promise<DecodedAudio> {
  const buffer = await file.arrayBuffer()
  const ctx = getAudioContext()
  if (ctx.state === 'suspended') await ctx.resume().catch(() => undefined)
  const audio = await ctx.decodeAudioData(buffer.slice(0))
  const channelData: Float32Array[] = []
  for (let c = 0; c < audio.numberOfChannels; c += 1) {
    channelData.push(audio.getChannelData(c))
  }
  const mono = mixToMono(channelData)
  return {
    sampleRate: audio.sampleRate,
    channels: audio.numberOfChannels,
    duration: audio.duration,
    peaks: buildPeaks(mono, peakBuckets),
    channelData,
  }
}

function mixToMono(channels: Float32Array[]): Float32Array {
  if (!channels.length) return new Float32Array(0)
  if (channels.length === 1) return channels[0]
  const len = channels[0].length
  const out = new Float32Array(len)
  const n = channels.length
  for (let i = 0; i < len; i += 1) {
    let sum = 0
    for (let c = 0; c < n; c += 1) sum += channels[c][i] ?? 0
    out[i] = sum / n
  }
  return out
}

function buildPeaks(samples: Float32Array, buckets: number): Float32Array {
  if (!samples.length) return new Float32Array(0)
  const count = Math.min(buckets, samples.length)
  const peaks = new Float32Array(count)
  const block = Math.max(1, Math.floor(samples.length / count))
  for (let i = 0; i < count; i += 1) {
    const start = i * block
    const end = Math.min(samples.length, start + block)
    let max = 0
    for (let j = start; j < end; j += 1) {
      const v = Math.abs(samples[j] ?? 0)
      if (v > max) max = v
    }
    peaks[i] = max
  }
  return peaks
}
