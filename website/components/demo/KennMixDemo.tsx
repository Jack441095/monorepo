"use client";

import { DemoPipeline } from "@/components/demo/DemoPipeline";
import { DemoShell } from "@/components/demo/DemoShell";
import { ReadoutPanel, ReadoutRow } from "@/components/demo/Readout";
import { useSignalDemo } from "@/components/demo/useSignalDemo";

/* KENN mix analysis demonstration — CONCEPT DEMO.

   KENN is in active research. This demonstration communicates the product
   idea — an assistant that reviews a mix and offers explainable
   suggestions — without implying shipped capability or live analysis.
   Confidence language only: Detected / Suggested / Review required. */

const DIMENSIONS = [
  { label: "LOW END", level: 0.82, tone: "review" as const, value: "Review recommended — energy builds below 80Hz", meter: "var(--brand-red)" },
  { label: "STEREO IMAGE", level: 0.64, tone: "ok" as const, value: "Healthy — balanced correlation across the field", meter: "var(--state-success)" },
  { label: "DYNAMICS", level: 0.74, tone: "info" as const, value: "Suggested — gentle glue compression on the chorus", meter: "var(--brand-blue-bright)" },
] as const;

export function KennMixDemo() {
  const { phase, start, reset } = useSignalDemo({ scanMs: 1300, analysisMs: 800 });
  const scanning = phase === "scanning";
  const analysing = phase === "analysis";
  const ready = phase === "result";
  const started = phase !== "idle";

  return (
    <DemoShell
      label="concept"
      title="KENN // MIX REVIEW"
      phase={phase}
      onReset={reset}
      ariaLabel="KENN mix analysis concept demonstration"
      footerNote="Concept demonstration — KENN is in active research. Values shown are illustrative."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-4">
        <DemoPipeline phase={phase} />

        {/* Input */}
        <div className="flex items-center justify-between gap-3 border border-border rounded px-4 py-3 bg-surface-raised/40">
          <span className="min-w-0">
            <span className="block text-[12px] font-mono text-foreground truncate">Summit_Mix_v7.wav</span>
            <span className="block text-[10px] font-mono text-muted-dim mt-0.5">Stereo bounce · 24-bit</span>
          </span>
          <button
            type="button"
            onClick={start}
            disabled={scanning || analysing}
            className="btn-primary text-[11px] px-3 py-1.5 flex-none disabled:opacity-50 disabled:cursor-default"
          >
            {scanning ? "SCANNING…" : analysing ? "ANALYSING…" : ready ? "Re-run" : "Run mix analysis"}
          </button>
        </div>

        {/* Analysis dimensions */}
        <div className="flex flex-col gap-3" aria-label="Mix dimensions">
          {DIMENSIONS.map((d) => (
            <div key={d.label}>
              <div className="flex items-center justify-between gap-3 mb-1.5">
                <span className="text-[10px] font-mono tracking-wider text-muted-dim uppercase">{d.label}</span>
                <span
                  className="text-[10px] font-mono"
                  style={{ color: ready ? "var(--foreground)" : "var(--muted-dim)" }}
                  aria-live="polite"
                >
                  {scanning ? "Scanning…" : analysing ? "Forming view…" : ready ? d.value.split(" — ")[0] : "—"}
                </span>
              </div>
              <div
                className="demo-meter"
                role="img"
                aria-label={`${d.label} level ${ready ? `${Math.round(d.level * 100)} percent` : "pending"}`}
              >
                <div
                  className="demo-meter__fill"
                  style={{
                    width: `${d.level * 100}%`,
                    background: d.meter,
                    transform: started ? "scaleX(1)" : "scaleX(0.12)",
                    opacity: ready ? 1 : 0.45,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Recommendation readout */}
        {ready && (
          <ReadoutPanel ariaLabel="Mix review recommendations">
            {DIMENSIONS.map((d) => (
              <ReadoutRow key={d.label} label={d.label} tone={d.tone}>
                {d.value}
              </ReadoutRow>
            ))}
            <ReadoutRow label="SUMMARY" tone="info">
              1 review required · 1 healthy · 1 suggested
            </ReadoutRow>
          </ReadoutPanel>
        )}

        {/* The message — assistive, never replacement */}
        <p className="text-[11px] font-mono text-muted-dim leading-relaxed">
          KENN assists engineers. KENN does not replace engineers — every
          suggestion comes with the reasoning, and every decision stays yours.
        </p>
      </div>
    </DemoShell>
  );
}
