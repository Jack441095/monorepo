import type { KennActionProposal } from '../api/kenn'

/** Return observed names and positions for a producer to approve an exact Live target. */
export function formatActionTarget(target: KennActionProposal): string {
  const track = target.track_name ?? `Track ${(target.track_index ?? 0) + 1}`
  const label = target.target_label ?? (target.device_name ? `${track} / ${target.device_name}` : track)
  const address = target.target_address
  if (!address) return label // Mixer proposals have no device or rack path to disambiguate.
  // Live's names can repeat at every level; retain one-based observed positions on both card types.
  const bus = address.kind === 'master' ? 'Master' : `${address.kind === 'return' ? 'Return' : 'Track'} ${address.index + 1}`
  const path = address.device_path.map((index, depth) => `${depth % 2 === 0 ? 'device' : 'chain'} ${index + 1}`).join(' / ')
  const parameter = target.parameter_index != null ? ` / parameter ${target.parameter_index + 1}` : ''
  return `${label} (${bus}, ${path}${parameter})`
}
