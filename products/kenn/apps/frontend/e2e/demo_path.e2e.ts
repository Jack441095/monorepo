import { expect, test } from '@playwright/test'
import { ask, openKenn } from './helpers'

// These drive the real chat UI end to end (chat → proposal card → Apply/Undo)
// against the fake Live backend. Each test restores what it changes.

test('session questions answer from the Live snapshot', async ({ page }) => {
  await openKenn(page)
  await expect(await ask(page, 'How many tracks do I have?')).toContainText('8 tracks')
  await expect(await ask(page, "What's selected?")).toContainText('Drum Bus')
})

test('Apply shows verified readback and receipt Undo restores it', async ({ page }) => {
  await openKenn(page)
  const reply = await ask(page, 'Set Compressor Output to 3 dB on track 7.')
  await reply.getByRole('button', { name: 'Apply to Live 12' }).click()
  await expect(reply).toContainText('Readback Verified')
  await reply.getByRole('button', { name: 'Undo' }).click()
  await expect(reply).toContainText('Restored to Original State')
})

test('Dismiss leaves Live unchanged', async ({ page }) => {
  await openKenn(page)
  const reply = await ask(page, 'Pan the Synth hard right.')
  await reply.getByRole('button', { name: 'Dismiss' }).click()
  await expect(reply).toContainText('No Changes Made')
  await expect(await ask(page, 'What did you change?')).toContainText("haven't made any changes")
})

test('chat "Undo that." reverts the change and marks its card', async ({ page }) => {
  await openKenn(page)
  const boost = await ask(page, 'Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.')
  await boost.getByRole('button', { name: 'Apply to Live 12' }).click()
  await expect(boost).toContainText('Readback Verified')
  const undo = await ask(page, 'Undo that.')
  await undo.getByRole('button', { name: 'Apply to Live 12' }).click()
  await expect(undo).toContainText('Readback Verified')
  await expect(boost).toContainText('Reverted')
  await expect(boost.getByRole('button', { name: 'Undo' })).toHaveCount(0)
})

test('destructive and master requests are refused without a proposal', async ({ page }) => {
  await openKenn(page)
  const del = await ask(page, 'Delete track 3.')
  await expect(del).toContainText('disabled by the KENN assistant boundary')
  await expect(del.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
  const master = await ask(page, 'Set the master volume to maximum.')
  await expect(master).toContainText('Nothing changed')
  await expect(master.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
})

test('a typed card label gets a short prompt, not a tutorial', async ({ page }) => {
  await openKenn(page)
  const reply = await ask(page, 'Try this')
  await expect(reply).toContainText('label from one of my cards')
  await expect(reply.getByRole('button', { name: 'Apply to Live 12' })).toHaveCount(0)
})

test('"Pan the Synth center." proposes pan centre and Dismiss changes nothing', async ({ page }) => {
  await openKenn(page)
  const reply = await ask(page, 'Pan the Synth center.')
  await expect(reply).toContainText('Synth')
  await reply.getByRole('button', { name: 'Dismiss' }).click()
  await expect(reply).toContainText('No Changes Made')
})

test('world-model questions answer returns and parameters in chat', async ({ page }) => {
  await openKenn(page)
  await expect(await ask(page, "What's on the A-Reverb return?")).toContainText('Hybrid Reverb')
  await expect(await ask(page, "What's the threshold on the Drum Bus compressor?")).toContainText('Threshold is')
})

test('generate chords as a confirmable MIDI clip, then undo it', async ({ page }) => {
  await openKenn(page)
  const track = await ask(page, 'Create a MIDI track.')
  await track.getByRole('button', { name: 'Apply to Live 12' }).click()
  await expect(track).toContainText('Readback Verified')
  const idea = await ask(page, 'Write a 4-bar chord progression in D minor')
  await expect(idea).toContainText('chord progression in D minor')
  await idea.getByRole('button', { name: 'Apply to Live 12' }).click()
  await expect(idea).toContainText('Readback Verified')
  await idea.getByRole('button', { name: 'Undo' }).click()
  await expect(idea).toContainText('Restored to Original State')
})
