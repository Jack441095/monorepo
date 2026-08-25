import type { ReactNode } from "react";

/* NITE Signal Demonstration Framework — readout rows.

   Confidence language is a hard rule: demos may say Detected / Suggested /
   Review required / Unknown — never Perfect / Guaranteed / Fully automatic.
   Meaning is carried by the glyph (✓ / ! / ·) as well as colour, so it
   survives colour-blindness and monochrome rendering. */

export type ReadoutTone = "ok" | "review" | "info" | "pending" | "muted";

const TONE_STYLE: Record<ReadoutTone, { ledClass: string; color: string }> = {
  ok: { ledClass: "dsp-led--green", color: "var(--state-success)" },
  review: { ledClass: "dsp-led--amber", color: "var(--state-warning)" },
  info: { ledClass: "dsp-led--green", color: "var(--brand-blue-bright)" },
  pending: { ledClass: "dsp-led", color: "var(--muted-dim)" },
  muted: { ledClass: "dsp-led", color: "var(--muted-dim)" },
};

export function ReadoutRow({
  label,
  children,
  tone = "info",
}: {
  label: string;
  children: ReactNode;
  tone?: ReadoutTone;
  glyph?: string;
}) {
  const t = TONE_STYLE[tone];
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-border/40 last:border-b-0">
      <span className="text-[10px] font-mono tracking-wider text-muted-dim uppercase pt-0.5">
        {label}
      </span>
      <span className="flex items-center gap-2 text-[11px] font-sans text-right min-w-0">
        <span aria-hidden="true" className={`dsp-led ${t.ledClass} flex-none`} />
        <span className="min-w-0 font-medium" style={{ color: tone === "muted" ? "var(--muted-dim)" : "var(--foreground)" }}>
          {children}
        </span>
      </span>
    </div>
  );
}

export function ReadoutPanel({ children, ariaLabel }: { children: ReactNode; ariaLabel?: string }) {
  return (
    <div className="border border-border rounded bg-surface-raised/40 px-4 py-2.5" aria-label={ariaLabel}>
      {children}
    </div>
  );
}
