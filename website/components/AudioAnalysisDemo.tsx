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
    centroid: "82 Hz",
    riseTime: "0.8 ms",
    tonalPitch: "G#1",
    decayTime: "240 ms",
    matches: ["Kick_012.wav", "Punch_205.wav", "Thump_77.wav"],
  },
  {
    filename: "take_new_001.wav",
    category: "SNARE",
    waveform: [0, 5, 80, 95, 70, 85, 60, 75, 50, 40, 30, 25, 20, 15, 12, 10, 8, 5, 2, 0, 0, 0, 0, 0],
    transientIdx: 3,
    color: "var(--brand-red)",
    centroid: "1.4 kHz",
    riseTime: "1.6 ms",
    tonalPitch: "A3",
    decayTime: "180 ms",
    matches: ["Snare_04.wav", "Rim_11.wav", "Clap_302.wav"],
  },
  {
    filename: "audio_219.wav",
    category: "SYNTH PAD",
    waveform: [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35],
    transientIdx: 14,
    color: "var(--brand-blue-bright)",
    centroid: "850 Hz",
    riseTime: "25.0 ms",
    tonalPitch: "F#2",
    decayTime: "1.8 s",
    matches: ["Pad_51.wav", "Warm_220.wav", "Drone_8.wav"],
  },
] as const;

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
            <svg viewBox="0 0 400 100" className="w-full h-full overflow-visible" preserveAspectRatio="none" aria-hidden="true">
              {/* Audio Frequency Grid Overlay */}
              <line x1="0" y1="25" x2="400" y2="25" stroke="var(--border)" strokeWidth="0.5" strokeDasharray="3,6" />
              <line x1="0" y1="50" x2="400" y2="50" stroke="var(--border)" strokeWidth="0.5" strokeDasharray="3,6" />
              <line x1="0" y1="75" x2="400" y2="75" stroke="var(--border)" strokeWidth="0.5" strokeDasharray="3,6" />
              
              <text x="5" y="18" fill="var(--muted-dim)" fontSize="7" className="font-mono">0 dB</text>
              <text x="5" y="44" fill="var(--muted-dim)" fontSize="7" className="font-mono">-12 dB</text>
              <text x="5" y="69" fill="var(--muted-dim)" fontSize="7" className="font-mono">-36 dB</text>
              <text x="5" y="94" fill="var(--muted-dim)" fontSize="7" className="font-mono">-Infinity</text>

              {/* Main signal envelope path */}
              <path
                d={sample.waveform.reduce((acc, val, idx) => {
                  const x = (idx / (sample.waveform.length - 1)) * 400;
                  const y = 90 - (val / 100) * 75;
                  return `${acc} ${idx === 0 ? "M" : "L"} ${x} ${y}`;
                }, "")}
                fill="none"
                stroke={revealed ? "var(--brand-blue)" : "var(--border-strong)"}
                strokeWidth="1.5"
                className="transition-all duration-300"
              />

              {/* Scanning analysis sweep */}
              {(scanning || phase === "analysis") && (
                <>
                  <path
                    d={sample.waveform.reduce((acc, val, idx) => {
                      const pct = (idx / (sample.waveform.length - 1)) * 100;
                      if (pct > scanProgress) return acc;
                      const x = (idx / (sample.waveform.length - 1)) * 400;
                      const y = 90 - (val / 100) * 75;
                      return `${acc} ${idx === 0 ? "M" : "L"} ${x} ${y}`;
                    }, "")}
                    fill="none"
                    stroke="var(--brand-violet)"
                    strokeWidth="2"
                  />
                  <line
                    x1={`${scanProgress}%`}
                    y1="0"
                    x2={`${scanProgress}%`}
                    y2="100"
                    stroke="var(--brand-blue-bright)"
                    strokeWidth="1.5"
                    style={{ filter: "drop-shadow(0 0 4px var(--brand-blue-bright))" }}
                  />
                </>
              )}

              {/* Transient detection coordinate node */}
              {revealed && (
                <>
                  <line
                    x1={(sample.transientIdx / (sample.waveform.length - 1)) * 400}
                    y1="0"
                    x2={(sample.transientIdx / (sample.waveform.length - 1)) * 400}
                    y2="100"
                    stroke={sample.color}
                    strokeWidth="0.75"
                    strokeDasharray="2,2"
                  />
                  <circle
                    cx={(sample.transientIdx / (sample.waveform.length - 1)) * 400}
                    cy={90 - (sample.waveform[sample.transientIdx] / 100) * 75}
                    r="4"
                    fill={sample.color}
                    className="animate-pulse"
                  />
                </>
              )}
            </svg>
          </div>
        </div>

        {/* Analysis readouts */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1 font-mono tnum">
          <ReadoutPanel ariaLabel="Acoustic analysis">
            <ReadoutRow
              label="SPECTRAL CENTROID"
              tone={revealed ? "info" : scanning ? "pending" : "muted"}
            >
              {scanning ? "CALCULATING…" : phase === "analysis" ? "MEASURING…" : revealed ? sample.centroid : "—"}
            </ReadoutRow>
            <ReadoutRow label="TRANSIENT RISE TIME" tone={revealed ? "info" : "muted"}>
              {scanning ? "DETECTING…" : phase === "analysis" ? "CORRELATING…" : revealed ? sample.riseTime : "—"}
            </ReadoutRow>
            <ReadoutRow label="TONAL PITCH CENTER" tone={revealed ? "info" : "muted"}>
              {scanning ? "TRACKING…" : phase === "analysis" ? "DETECTING…" : revealed ? sample.tonalPitch : "—"}
            </ReadoutRow>
            <ReadoutRow label="DECAY ENVELOPE" tone={revealed ? "info" : "muted"}>
              {scanning ? "MEASURING…" : phase === "analysis" ? "CALCULATING…" : revealed ? sample.decayTime : "—"}
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
