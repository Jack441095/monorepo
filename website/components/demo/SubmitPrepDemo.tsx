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
    kind: "PDF document · 2.4 MB",
    path: "~/Documents/Uni/MOD402/Assignment_Final.pdf",
    modified: "2026-08-24 14:32",
    outputPreview: "2026_MOD402_1048291_Assignment.pdf",
    findings: [
      { label: "DOCUMENT TYPE", tone: "ok" as const, status: "VERIFIED", value: "Assignment brief — PDF/A-1b" },
      { label: "STUDENT IDENTITY", tone: "ok" as const, status: "VERIFIED", value: "Name & ID header verified (ID: 1048291)" },
      { label: "MODULE CODE", tone: "ok" as const, status: "VERIFIED", value: "MOD402 found on page 1" },
      { label: "FILENAME SANITIZER", tone: "review" as const, status: "REVIEW NEEDED", value: "Remove redundant 'Final' tag from filename" },
      { label: "LOCAL READINESS", tone: "ok" as const, status: "VERIFIED", value: "Ready for user verification & approval" },
    ],
  },
  {
    name: "Thesis_Chapter2.docx",
    kind: "Word document · 1.8 MB",
    path: "~/Documents/Thesis/Drafts/Thesis_Chapter2.docx",
    modified: "2026-08-25 09:15",
    outputPreview: "2026_THES701_1048291_Chapter2.pdf",
    findings: [
      { label: "DOCUMENT TYPE", tone: "ok" as const, status: "VERIFIED", value: "Chapter draft — DOCX" },
      { label: "STUDENT IDENTITY", tone: "review" as const, status: "REVIEW NEEDED", value: "Student name header missing" },
      { label: "MODULE CODE", tone: "ok" as const, status: "VERIFIED", value: "THES701 cover page verified" },
      { label: "EMBEDDED COMMENTS", tone: "info" as const, status: "SUGGESTED", value: "2 unresolved reviewer comments" },
      { label: "LOCAL READINESS", tone: "review" as const, status: "REVIEW NEEDED", value: "Resolve name header before export" },
    ],
  },
  {
    name: "portfolio_2026.zip",
    kind: "Zip Archive · 14.2 MB",
    path: "~/Desktop/portfolio_2026.zip",
    modified: "2026-08-23 18:40",
    outputPreview: "2026_PORT800_1048291_Portfolio.zip",
    findings: [
      { label: "ARCHIVE TYPE", tone: "ok" as const, status: "VERIFIED", value: "ZIP Archive — 14 files" },
      { label: "FILE FORMATS", tone: "review" as const, status: "REVIEW NEEDED", value: "Contains unsupported .pages & .cad files" },
      { label: "TOTAL SIZE", tone: "info" as const, status: "VERIFIED", value: "14.2 MB — Within 50MB portal limit" },
      { label: "LOCAL READINESS", tone: "review" as const, status: "REVIEW NEEDED", value: "Convert unsupported files before export" },
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
      title="SUBMIT // PREPARATION CONSOLE"
      phase={phase}
      onReset={reset}
      ariaLabel="Submit document preparation console demonstration"
      footerNote="Simulated console demonstration with illustrative data. Documents are verified strictly on local hardware."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-5">
        <DemoPipeline phase={phase} />

        {/* Local Security & Privacy Seal Bar */}
        <div className="flex items-center justify-between gap-2 px-3.5 py-2 rounded bg-surface-raised/80 border border-border-strong/50 text-[10px] font-mono">
          <div className="flex items-center gap-2">
            <span className="dsp-led dsp-led--live" />
            <span className="text-foreground font-bold uppercase tracking-wider">LOCAL CHECK ONLY</span>
          </div>
          <div className="flex items-center gap-3 text-muted-dim">
            <span className="text-brand-emerald font-bold">0 BYTES UPLOADED</span>
            <span>USER APPROVES EXPORT</span>
          </div>
        </div>

        {/* Input — Document Selection Rack */}
        <div className="flex flex-col gap-2.5" role="group" aria-label="Choose a document to check">
          <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
            SELECT LOCAL INPUT FILE
          </span>
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
                className={`demo-filechip flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-all cursor-pointer disabled:cursor-default ${
                  active
                    ? "border-brand-blue bg-brand-blue/10 shadow-[0_0_15px_rgba(0,240,255,0.12)]"
                    : "border-border/60 bg-surface/50 hover:border-border-strong"
                }`}
                style={active && started ? ({ ["--scan" as string]: scanning ? "1" : analysing ? "1" : "0" } as React.CSSProperties) : undefined}
              >
                <span className="min-w-0">
                  <span className="block text-[12px] font-mono text-foreground font-bold truncate">{f.name}</span>
                  <span className="block text-[10px] font-sans text-muted-dim mt-0.5">{f.kind}</span>
                </span>
                <span
                  className="text-[10px] font-mono flex-none px-2.5 py-1 rounded bg-surface-raised border border-border/40 font-bold"
                  style={{ color: active ? "var(--brand-blue-bright)" : "var(--muted-dim)" }}
                >
                  {active && scanning
                    ? "SCANNING…"
                    : active && analysing
                      ? "ANALYSING…"
                      : active && ready
                        ? "READY"
                        : "CHECK FILE"}
                </span>
              </button>
            );
          })}
        </div>

        {/* Inspection Panel / Findings Rack */}
        {!started ? (
          <div className="dsp-lcd-box p-6 text-center">
            <p className="text-[11px] font-mono text-muted-dim leading-relaxed">
              Select a file above to inspect detected metadata, identity headers, and export readiness.
            </p>
          </div>
        ) : (
          <div className="dsp-rack-panel p-4 rounded-lg flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
                MODULE 01 // DETECTED METADATA FIELDS
              </span>
              <span className="text-[10px] font-mono text-muted-dim tnum">{file.modified}</span>
            </div>

            <ReadoutPanel ariaLabel="Preparation findings">
              {scanning ? (
                FILES[0].findings.map((f) => (
                  <ReadoutRow key={f.label} label={f.label} tone="pending">
                    <span className="text-muted-dim">Reading local bytes…</span>
                  </ReadoutRow>
                ))
              ) : analysing ? (
                <ReadoutRow label="ANALYSIS" tone="pending">
                  <span className="text-muted-dim">Correlating file structure and metadata headers…</span>
                </ReadoutRow>
              ) : (
                file.findings.map((f) => (
                  <ReadoutRow key={f.label} label={f.label} tone={f.tone}>
                    <div className="flex items-center justify-between w-full gap-2">
                      <span>{f.value}</span>
                      <span
                        className={`text-[9px] font-mono px-2 py-0.5 rounded uppercase font-bold flex-none ${
                          f.status === "VERIFIED"
                            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                            : f.status === "REVIEW NEEDED"
                            ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                            : "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                        }`}
                      >
                        {f.status}
                      </span>
                    </div>
                  </ReadoutRow>
                ))
              )}
            </ReadoutPanel>

            {/* Generated Output Filename LCD Box */}
            {ready && (
              <div className="mt-2 p-3.5 dsp-lcd-box rounded-lg flex flex-col gap-1.5">
                <span className="text-[9px] font-mono text-muted-dim uppercase tracking-wider">
                  MODULE 02 // SANITIZED OUTPUT FILENAME PREVIEW
                </span>
                <div className="flex items-center justify-between gap-2">
                  <code className="text-xs font-mono tnum text-brand-emerald font-bold select-all tracking-wide">
                    {file.outputPreview}
                  </code>
                  <span className="text-[9px] font-mono text-muted-dim px-2 py-0.5 rounded bg-surface border border-border/40">
                    PREPARED
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Claim-Safe Product Positioning Message */}
        <p className="text-[11px] font-mono text-muted-dim leading-relaxed border-t border-border/30 pt-3">
          Submit helps you prepare safely on local hardware. Submit never submits automatically—you check the details and execute the export when ready.
        </p>
      </div>
    </DemoShell>
  );
}
