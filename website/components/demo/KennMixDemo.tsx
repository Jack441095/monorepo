"use client";

import { useState } from "react";
import { DemoPipeline } from "@/components/demo/DemoPipeline";
import { DemoShell } from "@/components/demo/DemoShell";
import { useSignalDemo } from "@/components/demo/useSignalDemo";

/* KENN mix analysis demonstration, CONCEPT DEMO.

   KENN is in active research. This demonstration communicates the product
   idea, an assistant that reviews a mix and offers explainable
   suggestions, without implying shipped capability or live analysis.
   Confidence language only: Detected / Suggested / Review required. */

const DIMENSIONS = [
  {
    label: "LOW END (20-120 Hz)",
    level: 0.84,
    tone: "review" as const,
    status: "REVIEW RECOMMENDED",
    observation: "Sub-bass energy accumulating at 45Hz (+3.2dB excess over reference curve)",
    whyItMatters: "Consumes headroom and triggers master limiter pumping on bass transients",
    suggestion: "Apply a 24dB/oct high-pass filter at 30Hz or reduce low shelf by 1.8dB",
    meter: "var(--brand-red)",
  },
  {
    label: "STEREO CORRELATION (120-2kHz)",
    level: 0.68,
    tone: "ok" as const,
    status: "BALANCED FIELD",
    observation: "Phase coherence sits at +0.82 across the mid frequency spectrum",
    whyItMatters: "Mono compatibility is preserved across mobile and club sound systems",
    suggestion: "No adjustment needed, stereo width is stable",
    meter: "var(--state-success)",
  },
  {
    label: "DYNAMIC RANGE & CLARITY",
    level: 0.72,
    tone: "info" as const,
    status: "SUGGESTED TWEAK",
    observation: "Transient punch peak-to-RMS ratio is slightly squashed on chorus drop",
    whyItMatters: "Reduces punch perception on main snare and kick impact",
    suggestion: "Back off master glue compressor threshold by 1.5dB",
    meter: "var(--brand-blue-bright)",
  },
] as const;

export function KennMixDemo() {
  const { phase, start, reset } = useSignalDemo({ scanMs: 1300, analysisMs: 800 });
  const [selectedDimension, setSelectedDimension] = useState(0);
  const activeDim = DIMENSIONS[selectedDimension];

  const scanning = phase === "scanning";
  const analysing = phase === "analysis";
  const ready = phase === "result";
  const started = phase !== "idle";

  return (
    <DemoShell
      label="concept"
      title="KENN // MIX REVIEW ASSISTANT"
      phase={phase}
      onReset={reset}
      ariaLabel="KENN mix analysis concept demonstration"
      footerNote="Concept demonstration, KENN provides explainable mix feedback with acoustic reasoning. KENN does not replace the mix engineer."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-5">
        <DemoPipeline phase={phase} />

        {/* Input Signal Bar */}
        <div className="flex items-center justify-between gap-3 border border-border-strong/60 rounded-lg px-4 py-3 bg-surface-raised/60 dsp-rack-panel">
          <span className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="dsp-led dsp-led--live" />
              <span className="text-[12px] font-mono font-bold text-foreground truncate">
                Summit_Mix_v7.wav
              </span>
            </div>
            <span className="block text-[10px] font-sans text-muted-dim mt-0.5">
              Stereo bounce · 24-bit / 48kHz · 0dBFS Normalized
            </span>
          </span>
          <button
            type="button"
            onClick={start}
            disabled={scanning || analysing}
            className="btn-primary text-[11px] px-3.5 py-1.5 flex-none font-sans font-bold disabled:opacity-50 disabled:cursor-default"
          >
            {scanning ? "SCANNING SPECTRUM…" : analysing ? "FORMING VIEW…" : ready ? "RE-RUN ANALYSIS" : "RUN MIX REVIEW"}
          </button>
        </div>

        {/* SVG Multi-Band Frequency Spectrum Visualizer */}
        <div className="dsp-lcd-box p-4 rounded-lg flex flex-col gap-2">
          <div className="flex items-center justify-between text-[10px] font-mono text-muted-dim">
            <span className="font-bold text-brand-violet-text">FREQUENCY RESPONSE CURVE</span>
            <span className="tnum">20 Hz, 20 kHz</span>
          </div>

          <div className="relative w-full h-24 rounded bg-[#030509] border border-border/40 overflow-hidden">
            {/* Grid frequency lines */}
            <div className="absolute inset-0 flex justify-between px-4 pointer-events-none opacity-20 text-[8px] font-mono text-muted-dim">
              <span className="border-r border-muted-dim/40 h-full pr-1">100Hz</span>
              <span className="border-r border-muted-dim/40 h-full pr-1">1kHz</span>
              <span className="border-r border-muted-dim/40 h-full pr-1">5kHz</span>
              <span>15kHz</span>
            </div>

            {/* Simulated Frequency Curve SVG */}
            <svg className="w-full h-full" viewBox="0 0 400 100" preserveAspectRatio="none">
              <path
                d="M 0 65 Q 40 25, 80 50 T 160 45 T 240 55 T 320 40 L 400 60 L 400 100 L 0 100 Z"
                fill="rgba(168, 85, 247, 0.15)"
              />
              <path
                d="M 0 65 Q 40 25, 80 50 T 160 45 T 240 55 T 320 40 L 400 60"
                fill="none"
                stroke={started ? "#A855F7" : "rgba(168, 85, 247, 0.4)"}
                strokeWidth="2"
              />
              {/* Problem Marker at 45Hz */}
              {ready && (
                <g>
                  <circle cx="45" cy="35" r="4" fill="#EF4444" className="animate-ping opacity-75" />
                  <circle cx="45" cy="35" r="3" fill="#EF4444" />
                </g>
              )}
            </svg>
          </div>
        </div>

        {/* Analysis Dimensions & Meter Bars */}
        <div className="flex flex-col gap-3" aria-label="Mix dimensions">
          <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
            ACOUSTIC DIMENSIONS & FEEDBACK
          </span>

          {DIMENSIONS.map((d, idx) => {
            const isSelected = selectedDimension === idx;
            return (
              <button
                key={d.label}
                type="button"
                onClick={() => setSelectedDimension(idx)}
                className={`text-left p-3 rounded-lg border transition-all cursor-pointer ${
                  isSelected
                    ? "border-brand-violet bg-brand-violet/10 shadow-[0_0_12px_rgba(168,85,247,0.15)]"
                    : "border-border/60 bg-surface/40 hover:border-border-strong"
                }`}
              >
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <span className="text-[10px] font-mono font-bold tracking-wider text-foreground uppercase">
                    {d.label}
                  </span>
                  <span
                    className={`text-[9px] font-sans px-2 py-0.5 rounded font-bold ${
                      d.tone === "review"
                        ? "bg-red-500/15 text-red-400 border border-red-500/30"
                        : d.tone === "ok"
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                        : "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                    }`}
                  >
                    {ready ? d.status : scanning ? "SCANNING…" : "READY"}
                  </span>
                </div>
                <div className="demo-meter">
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
              </button>
            );
          })}
        </div>

        {/* Evidence Card Area (Observation -> Why It Matters -> Suggestion) */}
        {ready && (
          <div className="dsp-rack-panel p-4 rounded-lg flex flex-col gap-2.5 border-brand-violet/40">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand-violet-text">
                EVIDENCE-BASED MIX OBSERVATION
              </span>
              <span className="text-[10px] font-mono text-muted-dim">EXPLAINABLE ADVICE</span>
            </div>

            <div className="space-y-2 text-xs font-sans">
              <div className="p-2.5 dsp-lcd-box rounded">
                <span className="text-[9px] font-mono text-muted-dim uppercase block">OBSERVATION</span>
                <span className="text-foreground font-medium block mt-0.5">{activeDim.observation}</span>
              </div>
              <div className="p-2.5 dsp-lcd-box rounded">
                <span className="text-[9px] font-mono text-muted-dim uppercase block">WHY IT MATTERS</span>
                <span className="text-muted block mt-0.5 leading-relaxed">{activeDim.whyItMatters}</span>
              </div>
              <div className="p-2.5 dsp-lcd-box rounded border-brand-violet/30">
                <span className="text-[9px] font-mono text-brand-violet-text font-bold uppercase block">EXPLAINABLE SUGGESTION</span>
                <span className="text-brand-blue-bright font-semibold block mt-0.5">{activeDim.suggestion}</span>
              </div>
            </div>
          </div>
        )}

        {/* Positioning Disclaimer, Assistive tool, never auto-mix */}
        <p className="text-[11px] font-sans text-muted-dim leading-relaxed border-t border-border/30 pt-3">
          KENN offers evidence-based observations with clear acoustic explanations. KENN does not replace the mix engineer, every decision remains yours.
        </p>
      </div>
    </DemoShell>
  );
}
