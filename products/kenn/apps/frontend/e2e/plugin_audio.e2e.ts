import { expect, test, type APIRequestContext } from '@playwright/test'
import { ask } from './helpers'

// Generated feature frames stand in for two native inserts and an unrelated
// conversation. FakeLive alone supplies mixer readback; no Live/audio files are read.
async function featurePublisher(request: APIRequestContext, owner: string) {
  const inserts = [
    { id: `${owner}-kick`, owner, name: 'Kick', publishing: false, analysis: true, channels: 2, correlation: 0.3 },
    { id: `${owner}-bass`, owner, name: 'Bass', publishing: true, analysis: true, channels: 2, correlation: 0.7 },
    { id: `${owner}-foreign`, owner: `${owner}-other`, name: 'Kick', publishing: true, analysis: true, channels: 2, correlation: -0.5 },
  ]
  let sequence = 10 // Begin beyond the 8192-sample FFT warm-up interval at 48 kHz.
  let stopped = false
  let pending: Promise<void> | undefined
  let failure: unknown
  const pump = () => {
    if (stopped || pending) return pending // Neither delayed HTTP nor teardown may duplicate publication.
    pending = (async () => {
      for (const insert of inserts) {
        const response = await request.get(`/api/plugin/parameters?session_id=${insert.id}&pop_pending=1`)
        const updates = (await response.json()).pending_updates ?? {}
        if ('live_context_enabled' in updates) insert.publishing = updates.live_context_enabled
        if ('analysis_enabled' in updates) insert.analysis = updates.analysis_enabled
      }
      const end = ++sequence * 4800 // Samples: each fixture advances one complete 100 ms window.
      const frames = inserts.filter(insert => insert.publishing).map(insert => ({
        schema: 'kenn.plugin_handoff.v1', audio_feature_schema: 'audio_feature_frame.v1', kind: 'mix_review_snapshot',
        session_id: insert.id, conversation_id: insert.owner, host_track_name: insert.name, assistant_mode: 'suggest',
        peak_dbfs: -0.5, rms_dbfs: -16, stereo_correlation: insert.correlation, stereo_width: 0.2,
        input_channels: insert.channels, correlation_valid: insert.channels === 2,
        sample_rate: 48000, analysed_samples: end, audio_age_seconds: 0,
        plugin_state: { assistant_mode: 'suggest', analysis_enabled: insert.analysis, live_context_enabled: insert.publishing },
        measurement_window: { schema: 'kenn.continuous_window.v1', valid: true, sequence, source_generation: 1,
          input_channels: insert.channels, correlation_valid: insert.channels === 2,
          start_sample: end - 4800, end_sample: end, duration_seconds: 0.1, dropped_samples: 0, invalid_samples: 0,
          host_timeline: { schema: 'kenn.host_timeline.v1', valid: true, transport_epoch: 2, start_sample: end - 4800, end_sample: end } },
        fft_spectra: { schema: 'kenn.fft_spectra.v1', fast: null, low: {
          size_samples: 8192, start_sample: end - 8192, end_sample: end, bin_hz: 48000 / 8192,
          mean_square: 0.125, peak_hz: 10 * 48000 / 8192, band_power: Array.from({ length: 32 }, (_, i) => i === 5 ? 0.125 : 0),
        } },
      }))
      if (frames.length) {
        const response = await request.post('/api/plugin-handoff-batch', { data: {
          schema: 'kenn.plugin_handoff_batch.v1', exported_at_epoch: Date.now() / 1000, frames,
        } })
        expect(response.ok()).toBeTruthy()
        expect((await response.json()).ok).toBe(true)
      }
    })().finally(() => { pending = undefined })
    return pending
  }
  await pump()
  // Publish at the native 2 Hz rate, well below the feature batch budget.
  const timer = setInterval(() => {
    void pump()?.catch(error => { failure = error; stopped = true })
  }, 500)
  return {
    inserts,
    async stop() { stopped = true; clearInterval(timer); await pending; if (failure) throw failure },
  }
}

test('explicit insert audio reaches browser advice, approved Apply/readback/Undo and pause', async ({ page }) => {
  test.setTimeout(90_000)
  const owner = `browser-audio-${Date.now()}`
  const publisher = await featurePublisher(page.request, owner)
  try {
    // These unrelated panels discover local projects even in FakeLive mode.
    // Keep this browser fixture independent of the producer's private files.
    await page.route(/\/api\/ableton\/(project-audio(?:\/poll)?|session-tracks)(?:\?|$)/, route => route.fulfill({
      json: { ok: true, project_name: 'Generated audio fixture', project_dir: '', bounces: [], tracks: [] },
    }))
    await page.goto(`/?session_id=${owner}&plugin_session_id=${owner}-kick`)
    // The first Chrome page also starts the workspace's session requests;
    // allow its cold start without changing the one-second audio freshness rule.
    await expect(page.getByText('Live connected')).toBeVisible({ timeout: 30_000 })
    const audio = page.getByRole('region', { name: 'Insert audio analysis' })
    const grade = audio.getByRole('region', { name: 'Selected insert grade' })
    const selector = audio.getByLabel('Audio source')
    await expect(selector).toHaveValue(`${owner}-kick`)
    await expect(audio).toContainText('Waiting for publication')
    await expect(grade).toContainText('Not graded')
    await expect(grade).not.toContainText('points available')
    // Bass published first: the browser must keep the explicit, unpublished Kick.
    await expect(selector.locator('option')).toHaveCount(2)
    await expect(selector).not.toContainText('foreign')
    await audio.getByRole('button', { name: 'Start audio analysis' }).click()
    await expect(audio).toContainText('Fresh audio')
    await expect(grade).toContainText('5.1 of 6 points available · 100 possible')
    await expect(grade).toContainText('Selected insert · Kick · 100 ms window')
    await expect(grade).toContainText('Declared target: Not graded')
    await expect(grade).toContainText('Reference match: Not graded')
    await expect(grade).toContainText('Tier: judgement')
    await expect(grade).toContainText('[0.25, 0.5)')
    await page.screenshot({ path: test.info().outputPath('insert-partial-grade.png'), fullPage: true })
    // Mono must abstain instead of earning stereo points from a placeholder.
    publisher.inserts[0]!.channels = 1
    await expect(grade).toContainText('Stereo input layout is missing or mono')
    await expect(grade).not.toContainText('5.1 of 6 points available')
    publisher.inserts[0]!.channels = 2
    await expect(grade).toContainText('5.1 of 6 points available')
    const reply = await ask(page, 'Analyse the kick and tell me what to change')
    await expect(reply).toContainText("Measured at 'Kick': sample peak -0.5 dBFS, 100 ms RMS -16.0 dBFS")
    await reply.getByRole('button', { name: 'Apply to Live 12' }).click()
    await expect(reply).toContainText('Readback Verified')
    await page.screenshot({ path: test.info().outputPath('insert-audio-analysis.png'), fullPage: true })
    await reply.getByRole('button', { name: 'Undo' }).click()
    await expect(reply).toContainText('Restored to Original State')
    const wrongTrack = await ask(page, 'Analyse the bass')
    await expect(wrongTrack).toContainText("current insert reports 'Kick'")
    await expect(wrongTrack.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
    const unbound = await ask(page, 'Is the bass masking the kick?')
    await expect(unbound).toContainText('bind each insert')
    await expect(unbound.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
    await expect(await ask(page, 'bind this insert to track 1')).toContainText("Associated this insert with track 1 'Kick'")
    await selector.selectOption(`${owner}-bass`)
    await expect(grade).toContainText('Selected insert · Bass · 100 ms window')
    await expect(grade).toContainText('6 of 6 points available · 100 possible')
    await expect(grade).not.toContainText('5.1 of 6 points available')
    await expect(await ask(page, 'bind this insert to track 5')).toContainText("Associated this insert with track 5 'Bass'")
    const paired = await ask(page, 'Is the bass masking the kick?')
    await expect(paired).toContainText('does not prove audible masking')
    await expect(paired.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
    await audio.getByRole('button', { name: 'Pause audio analysis' }).click()
    await expect(audio).toContainText('Pause requested')
    await expect(grade).toContainText('Not graded')
    await expect(grade).not.toContainText('6 of 6 points available')
    await expect.poll(() => publisher.inserts.find(insert => insert.id === `${owner}-bass`)?.analysis).toBe(false)
    const paused = await ask(page, 'Analyse the bass')
    await expect(paused).toContainText('no current audio measurement')
    await expect(paused.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
    await selector.selectOption(`${owner}-kick`)
    await publisher.stop()
    await expect(audio).toContainText('Audio stale or paused', { timeout: 5000 })
    await expect(grade).toContainText('Not graded')
    await expect(grade).not.toContainText('5.1 of 6 points available')
    const stale = await ask(page, 'Analyse the kick')
    await expect(stale).toContainText('no current audio measurement')
    await expect(stale.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
    // A forged launch cannot use another conversation's audio, even with its exact ID.
    await page.goto(`/?session_id=${owner}&plugin_session_id=${owner}-foreign`)
    await expect(page.getByRole('region', { name: 'Insert audio analysis' })).toContainText('another conversation')
    const foreign = await ask(page, 'Analyse the kick')
    await expect(foreign).toContainText('another conversation')
    await expect(foreign.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
  } finally { await publisher.stop() }
})
