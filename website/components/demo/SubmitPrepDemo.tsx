"use client";

import { useState } from "react";
import { DemoPipeline } from "@/components/demo/DemoPipeline";
import { DemoShell } from "@/components/demo/DemoShell";
import { ReadoutPanel, ReadoutRow } from "@/components/demo/Readout";
import { useSignalDemo } from "@/components/demo/useSignalDemo";

/* Submit preparation demonstration — SIMULATION.

   The message is deliberate and claim-safe: Submit helps users PREPARE
   important files safely; it never submits automatically. All findings are
   illustrative; no document processing happens in the browser. */

const FILES = [
  {
    name: "Assignment_Final.pdf",
    kind: "PDF document",
    findings: [
      { label: "DOCUMENT TYPE", tone: "ok" as const, value: "Assignment brief — Detected" },
      { label: "STUDENT INFORMATION", tone: "ok" as const, value: "Name + ID header found" },
      { label: "MODULE INFORMATION", tone: "ok" as const, value: "Module code found — page 1" },
      { label: "FILENAME", tone: "review" as const, value: "Review required — remove “Final”" },
      { label: "READINESS", tone: "ok" as const, value: "Preparation ready" },
    ],
  },
  {
    name: "Thesis_Chapter2.docx",
    kind: "Word document",
    findings: [
      { label: "DOCUMENT TYPE", tone: "ok" as const, value: "Chapter draft — Detected" },
      { label: "STUDENT INFORMATION", tone: "review" as const, value: "Review required — name missing" },
      { label: "MODULE INFORMATION", tone: "ok" as const, value: "Module code found — cover page" },
      { label: "EMBEDDED NOTES", tone: "info" as const, value: "Suggested — 2 draft comments to resolve" },
      { label: "READINESS", tone: "review" as const, value: "Review required before submission" },
    ],
  },
  {
    name: "portfolio_2026.zip",
    kind: "Archive",
    findings: [
      { label: "ARCHIVE TYPE", tone: "ok" as const, value: "Zip archive — Detected" },
      { label: "CONTENTS", tone: "info" as const, value: "14 files — 2 unsupported formats" },
      { label: "UNSUPPORTED", tone: "review" as const, value: "Review required — .pages, .cad" },
      { label: "TOTAL SIZE", tone: "info" as const, value: "Within typical portal limits" },
      { label: "READINESS", tone: "review" as const, value: "Review required before submission" },
    ],
  },
] as const;

export function SubmitPrepDemo() {
  const { phase, start, reset } = useSignalDemo({ scanMs: 1200, analysisMs: 700 });
  const [fileIdx, setFileIdx] = useState(0);
  const file = FILES[fileIdx];
  const scanning = phase === "scanning";
  const analysing = phase === "analysis";
  const ready = phase === "result";
  const started = phase !== "idle";

  return (
    <DemoShell
      label="simulation"
      title="SUBMIT // PREPARATION CHECK"
      phase={phase}
      onReset={reset}
      ariaLabel="Submit document preparation demonstration"
      footerNote="Simulated demonstration with illustrative data. No documents are processed or uploaded."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-4">
        <DemoPipeline phase={phase} />

        {/* Input — document selection */}
        <div className="flex flex-col gap-2" role="group" aria-label="Choose a document to check">
          {FILES.map((f, idx) => {
            const active = fileIdx === idx;
            return (
              <button
                key={f.name}
                type="button"
                onClick={() => {
                  setFileIdx(idx);
                  start();
                }}
                aria-pressed={active}
                disabled={scanning || analysing}
                className={`demo-filechip flex items-center justify-between gap-3 px-4 py-3 rounded border text-left transition-all cursor-pointer disabled:cursor-default ${
                  active
                    ? "border-brand-blue bg-brand-blue/6"
                    : "border-border hover:border-border-strong"
                }`}
                style={active && started ? ({ ["--scan" as string]: scanning ? "1" : analysing ? "1" : "0" } as React.CSSProperties) : undefined}
              >
                <span className="min-w-0">
                  <span className="block text-[12px] font-mono text-foreground truncate">{f.name}</span>
                  <span className="block text-[10px] font-mono text-muted-dim mt-0.5">{f.kind}</span>
                </span>
                <span
                  className="text-[10px] font-mono flex-none"
                  style={{ color: active ? "var(--brand-blue-bright)" : "var(--muted-dim)" }}
                >
                  {active && scanning
                    ? "SCANNING…"
                    : active && analysing
                      ? "ANALYSING…"
                      : active && ready
                        ? "READY ✓"
                        : "CHECK"}
                </span>
              </button>
            );
          })}
        </div>

        {/* Analysis / Result */}
        {!started ? (
          <div className="border border-border rounded bg-surface-raised/40 px-4 py-6 text-center">
            <p className="text-[11px] font-mono text-muted-dim">
              Select a document to see how Submit prepares it for submission.
            </p>
          </div>
        ) : (
          <ReadoutPanel ariaLabel="Preparation findings">
            {scanning
              ? FILES[0].findings.map((f) => (
                  <ReadoutRow key={f.label} label={f.label} tone="pending">
                    <span className="text-muted-dim">Scanning…</span>
                  </ReadoutRow>
                ))
              : analysing
                ? (
                  <ReadoutRow label="ANALYSIS" tone="pending">
                    <span className="text-muted-dim">Correlating document structure…</span>
                  </ReadoutRow>
                )
                : (
                  file.findings.map((f) => (
                    <ReadoutRow key={f.label} label={f.label} tone={f.tone}>
                      {f.value}
                    </ReadoutRow>
                  ))
                )}
          </ReadoutPanel>
        )}

        {/* The message — preparation, never auto-submission */}
        <p className="text-[11px] font-mono text-muted-dim leading-relaxed">
          Submit helps you prepare safely. Submit does not submit automatically —
          you stay in control of every submission.
        </p>
      </div>
    </DemoShell>
  );
}
