import { expect, type Locator, type Page } from '@playwright/test'

export async function openKenn(page: Page) {
  await page.goto('/')
  await expect(page.getByText('Live connected')).toBeVisible()
}

/** Send one chat message and return the assistant reply bubble it produced. */
export async function ask(page: Page, text: string): Promise<Locator> {
  const replies = page.locator('.chat-message--assistant')
  const before = await replies.count()
  const input = page.getByPlaceholder('Type a message...')
  await input.fill(text)
  await input.press('Enter')
  await expect(replies).toHaveCount(before + 1, { timeout: 15_000 })
  return replies.nth(before)
}
