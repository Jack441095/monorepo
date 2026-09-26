// Volume proposals carry the level in dB as well as the raw fader value; people read Live's faders in dB.
export function formatDb(db: unknown): string | null {
  if (db === '-inf') return '-inf dB'
  return typeof db === 'number' && Number.isFinite(db) ? `${db.toFixed(1)} dB` : null
}
