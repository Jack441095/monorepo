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
