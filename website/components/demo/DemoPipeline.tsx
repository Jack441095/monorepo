import { type DemoPhase } from "./useSignalDemo";

/* NITE Signal Demonstration Framework — the shared pipeline strip.

   INPUT → ANALYSIS → INTELLIGENCE → RECOMMENDATION → ACTION

   Decorative by itself (aria-hidden): the same information is conveyed by
   the phase readout (aria-live) and the readout rows inside each demo.
   Stage labels collapse to dots below 640px so the strip can never cause
   horizontal overflow on phones; a screen-reader summary carries the rest. */

const STAGES = ["INPUT", "ANALYSIS", "INTELLIGENCE", "RECOMMENDATION", "ACTION"] as const;

const ACTIVE_STAGE: Record<DemoPhase, number> = {
  idle: 0,
  scanning: 1,
  analysis: 2,
  result: 4,
};

export function DemoPipeline({ phase }: { phase: DemoPhase }) {
  const active = ACTIVE_STAGE[phase];

  return (
    <div
      aria-hidden="true"
      className="flex items-center gap-1.5 sm:gap-2 px-5 pt-4 text-[9px] font-mono tracking-wider"
    >
      {STAGES.map((stage, i) => {
        const reached = i <= active && (phase !== "idle" || i === 0);
        const current = i === active && phase !== "idle";
        return (
          <div key={stage} className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            {i > 0 && (
              <span
                className="h-px flex-1 min-w-2 transition-colors duration-500"
                style={{
                  background: reached
                    ? i <= 2
                      ? "var(--brand-blue)"
                      : i === 3
                        ? "var(--brand-violet)"
                        : "var(--brand-red)"
                    : "var(--border)",
                  boxShadow: reached ? "0 0 6px rgba(57,123,255,0.35)" : "none",
                }}
              />
            )}
            <span
              className="w-1.5 h-1.5 rounded-full flex-none sm:hidden transition-colors duration-500"
              style={{
                background: current
                  ? "var(--brand-blue-bright)"
                  : reached
                    ? "var(--muted)"
                    : "var(--border-strong)",
              }}
            />
            <span
              className="whitespace-nowrap hidden sm:inline transition-colors duration-500"
              style={{
                color: current
                  ? "var(--brand-blue-bright)"
                  : reached
                    ? "var(--muted)"
                    : "var(--muted-dim)",
                opacity: reached ? 1 : 0.55,
              }}
            >
              {stage}
            </span>
          </div>
        );
      })}
      {/* Phase meaning is announced by DemoShell's aria-live readout; this
          strip is decoration and fully aria-hidden. */}
    </div>
  );
}
