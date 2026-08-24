import type { ReactNode } from "react";

/* NITE Signal Demonstration Framework — readout rows.

   Confidence language is a hard rule: demos may say Detected / Suggested /
   Review required / Unknown — never Perfect / Guaranteed / Fully automatic.
   Meaning is carried by the glyph (✓ / ! / ·) as well as colour, so it
   survives colour-blindness and monochrome rendering. */

export type ReadoutTone = "ok" | "review" | "info" | "pending" | "muted";

const TONE_STYLE: Record<ReadoutTone, { glyph: string; color: string }> = {
  ok: { glyph: "✓", color: "var(--state-success)" },
  review: { glyph: "!", color: "var(--state-warning)" },
  info: { glyph: "·", color: "var(--brand-blue-bright)" },
  pending: { glyph: "…", color: "var(--muted-dim)" },
  muted: { glyph: "·", color: "var(--muted-dim)" },
};

export function ReadoutRow({
  label,
  children,
  tone = "info",
  glyph,
}: {
  label: string;
  children: ReactNode;
  tone?: ReadoutTone;
  glyph?: string;
}) {
  const t = TONE_STYLE[tone];
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-border/40 last:border-b-0">
      <span className="text-[10px] font-mono tracking-wider text-muted-dim uppercase pt-0.5">
        {label}
      </span>
      <span className="flex items-start gap-2 text-[11px] font-mono text-right min-w-0">
        <span aria-hidden="true" className="flex-none pt-px" style={{ color: t.color }}>
          {glyph ?? t.glyph}
        </span>
        <span className="min-w-0" style={{ color: tone === "muted" ? "var(--muted-dim)" : "var(--foreground)" }}>
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
