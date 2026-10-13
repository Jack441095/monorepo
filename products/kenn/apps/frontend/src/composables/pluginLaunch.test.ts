import { describe, expect, it } from 'vitest'
import { readPluginLaunch } from './pluginLaunch'

describe('native plug-in launch identity', () => {
  it('keeps the native conversation and selected insert separate, including escaped names', () => {
    expect(readPluginLaunch('?session_id=song%20%26%20one&plugin_session_id=insert-uuid'))
      .toEqual({ sessionId: 'song & one', pluginSessionId: 'insert-uuid' })
  })

  it.each(['', '?session_id=owner', '?plugin_session_id=insert',
    '?session_id=a&session_id=b&plugin_session_id=insert', '?session_id=a&plugin_session_id=i&plugin_session_id=j',
    '?session_id=%0aowner&plugin_session_id=i', '?session_id=%20owner&plugin_session_id=i',
    `?session_id=${'x'.repeat(129)}&plugin_session_id=i`])('rejects an incomplete or ambiguous launch %s', search => {
    expect(readPluginLaunch(search)).toBeNull()
  })
})
