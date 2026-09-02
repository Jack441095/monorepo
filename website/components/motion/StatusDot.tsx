/* Status energy system, shape-first status cue.
   The dot carries the state (shape/motion), colour assists, and text always
   states it outright. Maturity labels stay still; the "live" dot only
   breathes on pointer attention of an owning spotlight-group card. */

const TONES = {
  live: "var(--brand-blue-bright)",
  muted: "var(--muted-dim)",
  warning: "var(--state-warning)",
} as const;

export function StatusDot({
  tone,
  live = false,
}: {
  tone: keyof typeof TONES;
  live?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={`status-chip__dot${live ? " status-chip__dot--live" : ""}`}
      style={{ color: TONES[tone], backgroundColor: TONES[tone] }}
    />
  );
}
