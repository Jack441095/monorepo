import { expect, test } from '@playwright/test'
import { openKenn } from './helpers'

function toneWav(frequencyHz: number): Buffer {
  // One second of mono PCM16 at 8 kHz keeps this an upload-path check, not a meter qualification.
  // The 44-byte PCM header uses byte offsets below; each 16-bit sample occupies two bytes.
  const sampleRate = 8000
  const dataBytes = sampleRate * 2
  const wav = Buffer.alloc(44 + dataBytes)
  wav.write('RIFF', 0)
  wav.writeUInt32LE(36 + dataBytes, 4)
  wav.write('WAVEfmt ', 8)
  wav.writeUInt32LE(16, 16)
  wav.writeUInt16LE(1, 20)
  wav.writeUInt16LE(1, 22)
  wav.writeUInt32LE(sampleRate, 24)
  wav.writeUInt32LE(sampleRate * 2, 28)
  wav.writeUInt16LE(2, 32)
  wav.writeUInt16LE(16, 34)
  wav.write('data', 36)
  wav.writeUInt32LE(dataBytes, 40)
  // 6000 PCM counts is about -14.7 dBFS peak: the reference grade changes with spectrum, not clipping.
  for (let frame = 0; frame < sampleRate; frame += 1) {
    wav.writeInt16LE(Math.round(6000 * Math.sin(2 * Math.PI * frequencyHz * frame / sampleRate)), 44 + frame * 2)
  }
  return wav
}

test('the upload Grade card follows the selected reference and clears it on the next mix-only review', async ({ page }, testInfo) => {
  // Folder discovery can auto-load a producer's bounce on mount; this test supplies only generated uploads.
  await page.route('**/api/ableton/project-audio**', (route) => route.fulfill({
    json: { ok: true, project_name: 'Upload regression', bounces: [], has_new: false },
  }))
  await openKenn(page)
  const inputs = page.locator('.mix-lab__inputs input[type="file"]')
  const mix = { name: 'mix.wav', mimeType: 'audio/wav', buffer: toneWav(100) }
  await inputs.nth(0).setInputFiles(mix)
  await inputs.nth(1).setInputFiles({ ...mix, name: 'reference.wav' })

  async function analyse() {
    // The browser uses the admin alias; both paths reach the same local upload handler.
    const response = page.waitForResponse((res) => /\/api\/(admin\/)?mix-review$/.test(res.url()) && res.request().method() === 'POST')
    await page.getByRole('button', { name: 'Analyse', exact: true }).click()
    const result = await (await response).json()
    expect(result.ok).toBe(true)
    await expect(page.locator('.mix-lab__status')).toHaveAttribute('data-state', 'completed')
    await expect(page.locator('.mix-lab__score strong')).toHaveText(String(result.review.grade.points))
    await expect(page.locator('.mix-lab__grade-meaning')).toHaveText(result.review.grade.meaning)
    return result.review.grade
  }

  const matched = await analyse()
  const referencePart = page.locator('.mix-lab__grade-parts li').filter({ hasText: 'Reference match' })
  await expect(referencePart).toContainText('30 / 30')
  await page.screenshot({ path: testInfo.outputPath('reference-grade.png'), fullPage: true })

  await inputs.nth(1).setInputFiles({ name: 'different.wav', mimeType: 'audio/wav', buffer: toneWav(3000) })
  const changed = await analyse()
  expect(changed.points).toBeLessThan(matched.points)
  await expect(referencePart).toBeVisible()

  await inputs.nth(1).setInputFiles([])
  await analyse()
  await expect(referencePart).toHaveCount(0)
  await expect(page.locator('.mix-lab__grade-meaning')).toContainText('no reference track supplied')
})
