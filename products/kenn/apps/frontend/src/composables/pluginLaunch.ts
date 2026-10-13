export type PluginLaunch = { sessionId: string; pluginSessionId: string }

/** Accept the native editor's paired identities; an ordinary browser keeps its fresh chat. */
export function readPluginLaunch(search: string): PluginLaunch | null {
  const query = new URLSearchParams(search)
  const owner = query.get('session_id') ?? ''
  const insert = query.get('plugin_session_id') ?? ''
  const valid = (value: string) => value.length > 0 && value.length <= 128
    && value === value.trim() && !/[\u0000-\u001f\u007f]/.test(value)
  if (query.getAll('session_id').length !== 1 || query.getAll('plugin_session_id').length !== 1
      || !valid(owner) || !valid(insert)) {
    // Incomplete/ambiguous links cannot grant an audio association to a fresh chat.
    return null
  }
  return { sessionId: owner, pluginSessionId: insert }
}
