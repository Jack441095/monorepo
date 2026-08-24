"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clamp, useReactivePointer } from "@/lib/motion";
import { DemoPipeline } from "@/components/demo/DemoPipeline";
import { DemoShell } from "@/components/demo/DemoShell";
import { ReadoutPanel, ReadoutRow } from "@/components/demo/Readout";
import { useSignalDemo } from "@/components/demo/useSignalDemo";

/* SLO intelligence demonstration — SIMULATION.

   Walks the shared signal path: a cryptic filename (INPUT) is scanned
   (ANALYSIS), described acoustically (INTELLIGENCE), classified with
   acoustic matches (RECOMMENDATION) — and the visitor understands the
   action SLO enables: finding sounds by sound. All values are illustrative
   and disclosed as such; similarity is qualitative (no fabricated metrics). */

const SAMPLES = [
  {
    filename: "XK29_0047.wav",
    category: "KICK",
    waveform: [20, 60, 90, 80, 50, 30, 15, 10, 5, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    transientIdx: 2,
    color: "var(--brand-red)",
    range: "45Hz – 12kHz",
    character: "Punchy / Electronic",
    matches: ["Kick_012.wav", "Punch_205.wav", "Thump_77.wav"],
  },
  {
    filename: "take_new_001.wav",
    category: "SNARE",
    waveform: [0, 5, 80, 95, 70, 85, 60, 75, 50, 40, 30, 25, 20, 15, 12, 10, 8, 5, 2, 0, 0, 0, 0, 0],
    transientIdx: 3,
    color: "var(--brand-red)",
    range: "120Hz – 16kHz",
    character: "Sharp / Snappy",
    matches: ["Snare_04.wav", "Rim_11.wav", "Clap_302.wav"],
  },
  {
    filename: "audio_219.wav",
    category: "SYNTH PAD",
    waveform: [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35],
    transientIdx: 14,
    color: "var(--brand-blue-bright)",
    range: "80Hz – 9kHz",
    character: "Warm / Sustained",
    matches: ["Pad_51.wav", "Warm_220.wav", "Drone_8.wav"],
  },
] as const;

/* Pseudo-analysis scramble shown only while scanning; derived from progress
   so it costs no extra state updates. */
function scramble(progress: number, seed: number): string {
  const digits = "0123456789";
  const a = digits[(Math.floor(progress * 7) + seed) % 10];
  const b = digits[(Math.floor(progress * 3) + seed * 3) % 10];
  const c = digits[(Math.floor(progress * 11) + seed * 7) % 10];
  return `${a}${b}.${c}`;
}

const SCAN_TICKS = 20;
const SCAN_TICK_MS = 40;

export function AudioAnalysisDemo() {
  const { phase, start, reset } = useSignalDemo({ scanMs: SCAN_TICKS * SCAN_TICK_MS, analysisMs: 600 });
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [scanProgress, setScanProgress] = useState(0);
  const [pulsing, setPulsing] = useState(false);
  const [chipPulseIdx, setChipPulseIdx] = useState(-1);

  const sample = SAMPLES[selectedIdx];
  const reactivePointer = useReactivePointer();
  const scanning = phase === "scanning";
  const revealed = phase === "result";

  /* Progress ticks only while the scanning phase is live. The reset to zero
     happens in the event handlers (selectSample/handleReset), never
     synchronously inside an effect. */
  useEffect(() => {
    if (!scanning) return;
    const interval = setInterval(() => {
      setScanProgress((prev) => Math.min(100, prev + 100 / SCAN_TICKS));
    }, SCAN_TICK_MS);
    return () => clearInterval(interval);
  }, [scanning]);

  /* Transient micro-pulse when analysis resolves (rAF-deferred). */
  useEffect(() => {
    if (phase !== "result") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const raf = requestAnimationFrame(() => setPulsing(true));
    const t = window.setTimeout(() => setPulsing(false), 260);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(t);
    };
  }, [phase]);

  const fireChipPulse = useCallback((idx: number) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setChipPulseIdx(idx);
    window.setTimeout(() => setChipPulseIdx(-1), 240);
  }, []);

  const selectSample = (idx: number) => {
    setSelectedIdx(idx);
    setScanProgress(0);
    fireChipPulse(idx);
    start();
  };

  const handleReset = () => {
    reset();
    setScanProgress(0);
  };

  /* Pointer-responsive examination band (event-driven, no loops). */
  const bandRef = useRef<HTMLDivElement>(null);
  const onWaveMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!reactivePointer) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      const x = clamp(event.clientX - bounds.left, 0, bounds.width);
      if (bandRef.current) {
        bandRef.current.style.transform = `translate3d(${x.toFixed(1)}px, -50%, 0)`;
        bandRef.current.style.opacity = "1";
      }
    },
    [reactivePointer],
  );
  const onWaveLeave = useCallback(() => {
    if (bandRef.current) bandRef.current.style.opacity = "0";
  }, []);

  return (
    <DemoShell
      label="simulation"
      title="DSP SIGNAL CLASSIFIER"
      phase={phase}
      onReset={handleReset}
      resetLabel="Reset"
      ariaLabel="SLO sample analysis demonstration"
      footerNote="* Illustrative workflow simulation. Visual scans and values represent interface behavior, not live test benchmarks."
    >
      <div className="p-5 sm:p-6 bg-surface flex flex-col gap-4">
        <DemoPipeline phase={phase} />

        {/* Sample Selection List */}
        <div className="grid grid-cols-3 gap-2" role="group" aria-label="Choose a sample to analyse">
          {SAMPLES.map((s, idx) => {
            const active = selectedIdx === idx;
            return (
              <button
                key={s.filename}
                type="button"
                onClick={() => selectSample(idx)}
                aria-pressed={active}
                className={`transient-pulse ${chipPulseIdx === idx ? "is-pulsing" : ""} py-3 px-3 text-[11px] font-mono text-center rounded border transition-all cursor-pointer ${
                  active
                    ? "border-brand-blue bg-brand-blue/6 text-foreground"
                    : "border-border hover:border-border-strong text-muted"
                }`}
                disabled={scanning}
              >
                {s.filename}
              </button>
            );
          })}
        </div>

        {/* Waveform View & Scanning Line */}
        <div
          className="relative h-32 border border-border bg-background rounded-md overflow-hidden flex items-center px-6"
          onPointerMove={onWaveMove}
          onPointerLeave={onWaveLeave}
        >
          <div className="absolute inset-0 grid grid-cols-12 grid-rows-4 opacity-[0.03] pointer-events-none">
            {Array.from({ length: 48 }).map((_, i) => (
              <div key={i} className="border-t border-l border-foreground" />
            ))}
          </div>

          {reactivePointer && (
            <div
              ref={bandRef}
              aria-hidden="true"
              className="absolute top-1/2 left-0 h-full w-24 pointer-events-none"
              style={{
                background: "radial-gradient(closest-side, rgba(86,168,255,0.14), transparent 75%)",
                transform: "translate3d(-200px, -50%, 0)",
                opacity: 0,
                transition: "transform 160ms var(--motion-easing), opacity var(--motion-slow) var(--motion-easing)",
              }}
            />
          )}

          <div className="w-full flex items-end justify-between h-20 relative">
            {sample.waveform.map((val, barIdx) => {
              const hasTransient = barIdx === sample.transientIdx;
              const isPassedByScanner = (barIdx / sample.waveform.length) * 100 <= scanProgress;

              let barColor = "var(--border-strong)";
              if (scanning || phase === "analysis") {
                if (isPassedByScanner) barColor = "var(--brand-violet)";
              } else if (revealed) {
                barColor = hasTransient ? sample.color : "var(--brand-blue)";
              }

              return (
                <div key={barIdx} className="flex-1 mx-[2px] flex flex-col items-center h-full justify-end">
                  {hasTransient && revealed && (
                    <span
                      className="w-1.5 h-1.5 rounded-full mb-1 animate-ping absolute"
                      style={{ backgroundColor: sample.color, bottom: `${val + 10}%` }}
                    />
                  )}
                  <div
                    className="w-full rounded-sm transition-all duration-300"
                    style={{
                      height: `${val}%`,
                      backgroundColor: barColor,
                      boxShadow: hasTransient && revealed ? `0 0 12px ${sample.color}` : "none",
                    }}
                  />
                </div>
              );
            })}

            {(scanning || phase === "analysis") && (
              <>
                <div
                  aria-hidden="true"
                  className="absolute top-0 bottom-0 left-0 pointer-events-none"
                  style={{
                    width: `${scanProgress}%`,
                    background:
                      "linear-gradient(to right, transparent 55%, rgba(113,72,232,0.16) 92%, rgba(86,168,255,0.22) 100%)",
                  }}
                />
                <div
                  className="absolute top-0 bottom-0 w-[2px] bg-brand-blue-bright"
                  style={{
                    left: `${scanProgress}%`,
                    boxShadow: "0 0 10px var(--brand-blue-bright)",
                  }}
                />
              </>
            )}
          </div>
        </div>

        {/* Analysis readouts */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1 font-mono tnum">
          <ReadoutPanel ariaLabel="Acoustic analysis">
            <ReadoutRow
              label="TRANSIENT"
              tone={revealed ? "review" : scanning ? "pending" : "muted"}
              glyph={revealed ? "!" : undefined}
            >
              {scanning ? "DETECTING…" : phase === "analysis" ? "CORRELATING…" : revealed ? "Detected" : "Waiting"}
            </ReadoutRow>
            <ReadoutRow label="FREQUENCY RANGE" tone={revealed ? "info" : "muted"}>
              {scanning ? `${scramble(scanProgress, 9)}Hz…` : phase === "analysis" ? "MEASURING…" : revealed ? sample.range : "—"}
            </ReadoutRow>
            <ReadoutRow label="RMS POWER" tone={revealed ? "info" : "muted"}>
              {scanning ? `-${scramble(scanProgress, 4)} dB` : revealed ? "-14.2 dB" : "—"}
            </ReadoutRow>
            <ReadoutRow label="CHARACTER" tone={revealed ? "info" : "muted"}>
              {scanning ? "FORMING…" : revealed ? sample.character : "—"}
            </ReadoutRow>
          </ReadoutPanel>

          <div className="border border-border p-4 rounded bg-surface-raised flex flex-col justify-center items-center text-center min-h-[7.5rem]">
            <span className="text-[10px] text-muted-dim tracking-wider uppercase">SLO CLASSIFIED AS</span>
            <div className="h-10 flex items-center justify-center mt-1">
              {scanning || phase === "analysis" ? (
                <div className="flex gap-1.5 items-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-violet animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-violet animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-violet animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              ) : revealed ? (
                <span
                  className={`transient-pulse ${pulsing ? "is-pulsing" : ""} text-sm font-bold tracking-widest text-foreground bg-brand-blue/10 px-4 py-1.5 rounded border border-brand-blue/20`}
                  style={{ textShadow: "0 0 10px rgba(57,123,255,0.3)" }}
                >
                  {sample.category}
                </span>
              ) : (
                <span className="text-muted-dim italic text-xs">Select a sample to begin</span>
              )}
            </div>

            {/* Similarity — qualitative matches, no fabricated metrics */}
            {revealed && (
              <div className="mt-3 pt-3 border-t border-border/50 w-full" aria-label="Acoustically similar samples">
                <span className="text-[9px] text-muted-dim tracking-wider uppercase block mb-2">
                  SIMILARITY — ACOUSTIC MATCHES
                </span>
                <div className="flex flex-wrap justify-center gap-1.5">
                  {sample.matches.map((m) => (
                    <span
                      key={m}
                      className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-brand-blue/25 text-brand-blue-bright bg-brand-blue/5"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </DemoShell>
  );
}
