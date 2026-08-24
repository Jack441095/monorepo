"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clamp, useReactivePointer } from "@/lib/motion";

const SAMPLES = [
  {
    filename: "XK29_0047.wav",
    category: "KICK",
    waveform: [20, 60, 90, 80, 50, 30, 15, 10, 5, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    transientIdx: 2,
    color: "var(--brand-red)",
  },
  {
    filename: "take_new_001.wav",
    category: "SNARE",
    waveform: [0, 5, 80, 95, 70, 85, 60, 75, 50, 40, 30, 25, 20, 15, 12, 10, 8, 5, 2, 0, 0, 0, 0, 0],
    transientIdx: 3,
    color: "var(--brand-red)",
  },
  {
    filename: "audio_219.wav",
    category: "SYNTH PAD",
    waveform: [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35],
    transientIdx: 14,
    color: "var(--brand-blue-bright)",
  },
] as const;

/* Pseudo-analysis scramble shown only while the illustrative scan runs.
   Derived from scan progress so it costs no extra state updates. */
function scramble(progress: number, seed: number): string {
  const digits = "0123456789";
  const a = digits[(Math.floor(progress * 7) + seed) % 10];
  const b = digits[(Math.floor(progress * 3) + seed * 3) % 10];
  const c = digits[(Math.floor(progress * 11) + seed * 7) % 10];
  return `${a}${b}.${c}`;
}

export function AudioAnalysisDemo() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(100);
  const [revealed, setRevealed] = useState(true);
  const [pulsing, setPulsing] = useState(false);
  const [chipPulseIdx, setChipPulseIdx] = useState(-1);

  const sample = SAMPLES[selectedIdx];
  const reactivePointer = useReactivePointer();

  /* Pointer-responsive waveform: a soft blue examination band follows the
     cursor across the display with a short CSS-eased trail — local amplitude
     emphasis, not a hard scanner. Event-driven transform writes only; no
     animation loop runs. */
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
    if (bandRef.current) {
      bandRef.current.style.opacity = "0";
    }
  }, []);

  /* Transient micro-pulse: one short red impulse when analysis resolves. */
  const fireTransient = useCallback((target: "badge" | number) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (target === "badge") {
      setPulsing(true);
      window.setTimeout(() => setPulsing(false), 240);
    } else {
      setChipPulseIdx(target);
      window.setTimeout(() => setChipPulseIdx(-1), 240);
    }
  }, []);

  const triggerScan = (idx: number) => {
    if (isScanning) return;
    setSelectedIdx(idx);
    setIsScanning(true);
    setScanProgress(0);
    setRevealed(false);
    fireTransient(idx);
  };

  useEffect(() => {
    if (!isScanning) return;

    const interval = setInterval(() => {
      setScanProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsScanning(false);
          setRevealed(true);
          fireTransient("badge");
          return 100;
        }
        return prev + 5;
      });
    }, 40);

    return () => clearInterval(interval);
  }, [isScanning, fireTransient]);

  return (
    <div className="product-frame w-full max-w-2xl mx-auto">
      {/* Header Bar */}
      <div className="product-frame__bar flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-brand-blue animate-pulse" />
          DSP SIGNAL CLASSIFIER
        </span>
        <span className="flex items-center gap-2">
          <span className="chip-neutral text-[9px]">SIMULATION</span>
          <span className="text-[10px] text-muted-dim font-mono">BETA 2.1 // OFFLINE ENGINE</span>
        </span>
      </div>

      {/* Demo Panel Area */}
      <div className="p-6 bg-surface flex flex-col gap-6">
        {/* Sample Selection List */}
        <div className="grid grid-cols-3 gap-2">
          {SAMPLES.map((s, idx) => {
            const active = selectedIdx === idx;
            return (
              <button
                key={s.filename}
                type="button"
                onClick={() => triggerScan(idx)}
                className={`transient-pulse ${chipPulseIdx === idx ? "is-pulsing" : ""} py-3 px-3 text-[11px] font-mono text-center rounded border transition-all cursor-pointer ${
                  active
                    ? "border-brand-blue bg-brand-blue/6 text-foreground"
                    : "border-border hover:border-border-strong text-muted"
                }`}
                disabled={isScanning}
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
          {/* Grid lines in background */}
          <div className="absolute inset-0 grid grid-cols-12 grid-rows-4 opacity-[0.03] pointer-events-none">
            {Array.from({ length: 48 }).map((_, i) => (
              <div key={i} className="border-t border-l border-foreground" />
            ))}
          </div>

          {/* Pointer examination band — soft local waveform illumination */}
          {reactivePointer && (
            <div
              ref={bandRef}
              aria-hidden="true"
              className="absolute top-1/2 left-0 h-full w-24 pointer-events-none"
              style={{
                background:
                  "radial-gradient(closest-side, rgba(86,168,255,0.14), transparent 75%)",
                transform: "translate3d(-200px, -50%, 0)",
                opacity: 0,
                transition:
                  "transform 160ms var(--motion-easing), opacity var(--motion-slow) var(--motion-easing)",
              }}
            />
          )}

          {/* Simulated Waveform bars */}
          <div className="w-full flex items-end justify-between h-20 relative">
            {sample.waveform.map((val, barIdx) => {
              const hasTransient = barIdx === sample.transientIdx;
              const isPassedByScanner = (barIdx / sample.waveform.length) * 100 <= scanProgress;

              let barColor = "var(--border-strong)";
              if (isScanning) {
                if (isPassedByScanner) {
                  barColor = "var(--brand-violet)";
                }
              } else if (revealed) {
                barColor = hasTransient ? sample.color : "var(--brand-blue)";
              }

              return (
                <div key={barIdx} className="flex-1 mx-[2px] flex flex-col items-center h-full justify-end">
                  {hasTransient && revealed && !isScanning && (
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
                      boxShadow: hasTransient && revealed && !isScanning
                        ? `0 0 12px ${sample.color}`
                        : "none",
                    }}
                  />
                </div>
              );
            })}

            {/* Scan overlay cursor with violet processing trail */}
            {isScanning && (
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

        {/* Analysis Readout */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 font-mono tnum">
          {/* Signal analysis data */}
          <div className="border border-border p-4 rounded bg-surface-raised/40 text-[11px] leading-relaxed text-muted">
            <div className="flex justify-between">
              <span>RMS POWER</span>
              <span className="text-foreground font-semibold">
                {isScanning ? `-${scramble(scanProgress, 4)} dB` : "-14.2 dB"}
              </span>
            </div>
            <div className="flex justify-between mt-1.5">
              <span>SPECTRAL CENTROID</span>
              <span className="text-foreground font-semibold">
                {isScanning ? `${scramble(scanProgress, 9)} kHz` : "1.85 kHz"}
              </span>
            </div>
            <div className="flex justify-between mt-1.5">
              <span>TRANSIENT DETECTED</span>
              <span className={`font-semibold transition-colors ${revealed && !isScanning ? "text-brand-red-bright" : "text-muted"}`}>
                {isScanning ? "CALCULATING..." : revealed ? "YES (12ms)" : "WAITING"}
              </span>
            </div>
          </div>

          {/* Classification Output */}
          <div className="border border-border p-4 rounded bg-surface-raised flex flex-col justify-center items-center text-center">
            <span className="text-[10px] text-muted-dim tracking-wider uppercase">SLO CLASSIFIED AS:</span>
            <div className="h-10 flex items-center justify-center mt-1">
              {isScanning ? (
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
                <span className="text-muted-dim italic text-xs">READY TO CLASSIFY</span>
              )}
            </div>
          </div>
        </div>
        <div className="text-[10px] text-muted-dim font-mono text-center pt-2 border-t border-border/30">
          * Illustrative workflow simulation. Visual scans and values represent interface behavior, not live test benchmarks.
        </div>
      </div>
    </div>
  );
}
