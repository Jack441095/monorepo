// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/kenn', () => ({
  askKenn: vi.fn().mockResolvedValue({ answer: 'Measured', suggestions: [], sources: [], findings: [], raw: {} }),
  getAnswerUpgrade: vi.fn(), confirmKennAction: vi.fn(), revokeKennConfirmation: vi.fn(), undoKennAction: vi.fn(),
  fetchKennSessionCard: vi.fn().mockResolvedValue({ ok: true, status: 'offline', tracks: [], raw: {} }),
  fetchPluginSources: vi.fn(), requestPluginAudio: vi.fn().mockResolvedValue(undefined),
}))

import { askKenn, fetchPluginSources, requestPluginAudio } from '../api/kenn'
import { insertGrade } from '../api/__fixtures__/pluginInsertGrade'

const sources = [
  { insert_id: 'kick-insert', host_track_name: 'Kick', audio_age_seconds: 0.1, current_for_diagnosis: true,
    requested_parameters: { live_context_enabled: true }, reported_parameters: { live_context_enabled: true } },
  { insert_id: 'bass-insert', host_track_name: 'Bass', audio_age_seconds: 1.2, current_for_diagnosis: false,
    requested_parameters: { live_context_enabled: true }, reported_parameters: { live_context_enabled: true } },
]

describe('web chat attached to a native insert', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.mocked(fetchPluginSources).mockReset().mockResolvedValue(sources)
    vi.mocked(askKenn).mockClear()
    vi.mocked(requestPluginAudio).mockClear()
    window.history.replaceState({}, '', '/?session_id=native-owner&plugin_session_id=kick-insert')
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    window.history.replaceState({}, '', '/')
  })

  it('asks with its launch owner and changes source only after an explicit selection', async () => {
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    await kenn.sendMessage('Analyse this insert')
    expect(askKenn).toHaveBeenLastCalledWith(expect.objectContaining({ sessionId: 'native-owner', pluginSessionId: 'kick-insert' }))
    kenn.selectPluginInsert('unknown-insert')
    expect(kenn.pluginInsertId.value).toBe('kick-insert')
    kenn.selectPluginInsert('bass-insert')
    await kenn.sendMessage('Analyse this insert')
    expect(askKenn).toHaveBeenLastCalledWith(expect.objectContaining({ sessionId: 'native-owner', pluginSessionId: 'bass-insert' }))
    expect(kenn.pluginAudioStatus.value).toBe('Audio stale or paused')
  })

  it('does not opt into publication on page load, and a pause is a request rather than a host acknowledgement', async () => {
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    expect(requestPluginAudio).not.toHaveBeenCalled()
    expect(kenn.pluginAudioStatus.value).toBe('Fresh audio')
    await kenn.setPluginAudioEnabled(false)
    expect(requestPluginAudio).toHaveBeenCalledWith('native-owner', 'kick-insert', false)
    expect(kenn.pluginAudioStatus.value).toBe('Pause requested')
  })

  it('keeps an unpublished launch selected instead of choosing the newest sibling', async () => {
    vi.mocked(fetchPluginSources).mockResolvedValue([sources[1]!])
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    expect(kenn.pluginInsertId.value).toBe('kick-insert')
    expect(kenn.selectedPluginSource.value).toBeUndefined()
    await kenn.setPluginAudioEnabled(true)
    expect(requestPluginAudio).toHaveBeenCalledWith('native-owner', 'kick-insert', true)
    expect(kenn.pluginAudioStatus.value).toBe('Waiting for audio')
  })

  it('clears fresh status and blocks controls when the companion rejects ownership', async () => {
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    vi.mocked(fetchPluginSources).mockRejectedValue(new Error('private implementation detail'))
    await kenn.refreshPluginSources()
    expect(kenn.pluginAudioStatus.value).toBe('Source unavailable')
    expect(kenn.selectedPluginSource.value).toBeUndefined()
    await kenn.setPluginAudioEnabled(true)
    expect(requestPluginAudio).not.toHaveBeenCalled()
  })

  it('expires the score locally while hidden, without another source poll', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchPluginSources).mockResolvedValue([{ ...sources[0]!, grading: insertGrade() }, sources[1]!])
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    expect(kenn.selectedPluginGrade.value?.grade.points_available).toBe(6)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    await vi.advanceTimersByTimeAsync(901) // Milliseconds: 0.1 s old evidence has 0.9 s left in its one-second lifetime.
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    expect(fetchPluginSources).toHaveBeenCalledTimes(1)
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })

  it('includes the response delay in the one-second evidence lifetime', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchPluginSources).mockImplementation(async () => {
      await new Promise(resolve => setTimeout(resolve, 950))
      return [{ ...sources[0]!, grading: insertGrade() }]
    })
    const kenn = (await import('./useKenn')).useKenn()
    const refresh = kenn.refreshPluginSources()
    await vi.advanceTimersByTimeAsync(950)
    await refresh
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
  })

  it('retires the score immediately when Pause is pending before HTTP acknowledgement', async () => {
    vi.mocked(fetchPluginSources).mockResolvedValue([{ ...sources[0]!, grading: insertGrade() }])
    let acknowledge!: () => void
    vi.mocked(requestPluginAudio).mockImplementationOnce(() => new Promise(resolve => { acknowledge = resolve }))
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    expect(kenn.selectedPluginGrade.value).toBeDefined()
    const pause = kenn.setPluginAudioEnabled(false)
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    acknowledge()
    await pause
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
  })

  it('rejects the first A response after selecting A to B to A', async () => {
    vi.mocked(fetchPluginSources).mockResolvedValue([{ ...sources[0]!, grading: insertGrade() }, sources[1]!])
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    let resolveOld!: (value: typeof sources) => void
    vi.mocked(fetchPluginSources).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const oldRefresh = kenn.refreshPluginSources()
    kenn.selectPluginInsert('bass-insert')
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    kenn.selectPluginInsert('kick-insert')
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    resolveOld([{ ...sources[0]!, grading: insertGrade() } as typeof sources[number]])
    await oldRefresh
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    await kenn.refreshPluginSources()
    expect(kenn.selectedPluginGrade.value?.insert_id).toBe('kick-insert')
  })

  it('retires a score on polling failure and ignores a late older poll', async () => {
    vi.mocked(fetchPluginSources).mockResolvedValue([{ ...sources[0]!, grading: insertGrade() }])
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    let resolveOld!: (value: typeof sources) => void
    vi.mocked(fetchPluginSources).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const oldRefresh = kenn.refreshPluginSources()
    vi.mocked(fetchPluginSources).mockRejectedValueOnce(new Error('Offline'))
    await kenn.refreshPluginSources()
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    resolveOld([{ ...sources[0]!, grading: insertGrade() } as typeof sources[number]])
    await oldRefresh
    expect(kenn.selectedPluginGrade.value).toBeUndefined()
    expect(kenn.pluginAudioStatus.value).toBe('Source unavailable')
  })

  it('ordinary browser pages keep a fresh chat and send no insert identity', async () => {
    window.history.replaceState({}, '', '/')
    const kenn = (await import('./useKenn')).useKenn()
    await kenn.refreshPluginSources()
    await kenn.sendMessage('Analyse this insert')
    expect(fetchPluginSources).not.toHaveBeenCalled()
    expect(askKenn).toHaveBeenCalledWith(expect.objectContaining({ pluginSessionId: undefined }))
    expect(vi.mocked(askKenn).mock.calls[0]![0].sessionId).not.toBe('native-owner')
  })
})
