import type { ReactNode } from "react";
import { PHASE_LABEL, type DemoPhase } from "./useSignalDemo";

/* NITE Signal Demonstration Framework — shared demo chrome.

   Every demonstration is framed as a piece of NITE DSP hardware with an
   honest label (SIMULATION / CONCEPT DEMO), a live phase readout, an
   accessible name, and a reset control. The label is part of the component
   contract: a demo without an honesty label cannot be built with this
   framework. */

export type DemoLabelTone = "simulation" | "concept";

const LABEL_TEXT: Record<DemoLabelTone, string> = {
  simulation: "SIMULATION",
  concept: "CONCEPT DEMO",
};

export function DemoShell({
  label,
  title,
  phase,
  onReset,
  resetLabel = "Reset demo",
  children,
  footerNote,
  ariaLabel,
}: {
  label: DemoLabelTone;
  title: string;
  phase: DemoPhase;
  onReset: () => void;
  resetLabel?: string;
  children: ReactNode;
  footerNote: ReactNode;
  ariaLabel: string;
}) {
  return (
    <div
      className="product-frame w-full max-w-2xl mx-auto"
      role="region"
      aria-label={`${ariaLabel} (demonstration)`}
    >
      <div className="product-frame__bar flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 min-w-0">
          <span
            aria-hidden="true"
            className={`w-2 h-2 rounded-full flex-none ${
              phase === "idle" ? "bg-brand-blue/60" : "bg-brand-blue animate-pulse"
            }`}
          />
          <span className="truncate">{title}</span>
        </span>
        <span className="flex items-center gap-2 flex-none">
          <span className="chip-neutral text-[9px]">{LABEL_TEXT[label]}</span>
          <span
            className="text-[10px] font-mono tnum"
            aria-live="polite"
            style={{ color: "var(--muted-dim)" }}
          >
            {PHASE_LABEL[phase]}
          </span>
        </span>
      </div>

      {children}

      <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-border">
        <div className="text-[10px] text-muted-dim font-mono min-w-0">{footerNote}</div>
        <button
          type="button"
          onClick={onReset}
          disabled={phase === "idle"}
          className="btn-secondary text-[11px] px-3 py-1.5 flex-none disabled:opacity-40 disabled:cursor-default"
        >
          {resetLabel}
        </button>
      </div>
    </div>
  );
}
