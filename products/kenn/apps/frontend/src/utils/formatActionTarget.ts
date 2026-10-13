import type { KennActionProposal } from '../api/kenn'

/** Return observed names and positions for a producer to approve an exact Live target. */
export function formatActionTarget(target: KennActionProposal): string {
  let defaultTarget = 'Track 1'
  if (target.target?.startsWith('ableton_song') || target.target === 'song' || target.action?.startsWith('jump_to') || target.target === 'ableton_playhead') {
    defaultTarget = 'Song'
  }
  const track = target.track_name ?? (typeof target.track_index === 'number' ? `Track ${target.track_index + 1}` : defaultTarget)
  const label = target.target_label ?? (target.device_name ? `${track} / ${target.device_name}` : track)
  const address = target.target_address
  if (!address) return label // Mixer proposals have no device or rack path to disambiguate.
  // Live's names can repeat at every level; retain one-based observed positions on both card types.
  const bus = address.kind === 'master' ? 'Master' : `${address.kind === 'return' ? 'Return' : 'Track'} ${address.index + 1}`
  const path = address.device_path.map((index, depth) => `${depth % 2 === 0 ? 'device' : 'chain'} ${index + 1}`).join(' / ')
  const parameter = target.parameter_index != null ? ` / parameter ${target.parameter_index + 1}` : ''
  return `${label} (${bus}, ${path}${parameter})`
}
