"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* ============================================================================
   NITE Signal Demonstration Framework, state machine

   Every product demonstration walks the same path:

     INPUT → ANALYSIS → INTELLIGENCE → RECOMMENDATION → ACTION

   expressed as phases: idle → scanning → analysis → result (+ reset).

   The machine is timer-driven with full cleanup, never runs per-frame React
   state updates, and treats phase changes as *content* (they remain
   meaningful under prefers-reduced-motion; only decorative transitions are
   suppressed there).
   ========================================================================== */

export type DemoPhase = "idle" | "scanning" | "analysis" | "result";

export const PHASE_LABEL: Record<DemoPhase, string> = {
  idle: "IDLE",
  scanning: "SCANNING",
  analysis: "ANALYSING",
  result: "RESULT READY",
};

export function useSignalDemo(options?: {
  /** Duration of the scanning phase in ms. */
  scanMs?: number;
  /** Duration of the analysis phase in ms. */
  analysisMs?: number;
}) {
  const scanMs = options?.scanMs ?? 1100;
  const analysisMs = options?.analysisMs ?? 700;
  const [phase, setPhase] = useState<DemoPhase>("idle");
  const [runCount, setRunCount] = useState(0);
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    for (const t of timers.current) window.clearTimeout(t);
    timers.current = [];
  }, []);

  const start = useCallback(() => {
    clearTimers();
    setPhase("scanning");
    setRunCount((n) => n + 1);
    timers.current.push(window.setTimeout(() => setPhase("analysis"), scanMs));
    timers.current.push(
      window.setTimeout(() => setPhase("result"), scanMs + analysisMs),
    );
  }, [clearTimers, scanMs, analysisMs]);

  const reset = useCallback(() => {
    clearTimers();
    setPhase("idle");
  }, [clearTimers]);

  useEffect(() => clearTimers, [clearTimers]);

  return { phase, start, reset, runCount, busy: phase === "scanning" || phase === "analysis" };
}
