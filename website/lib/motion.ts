"use client";

import { useEffect, useState } from "react";

/* ============================================================================
   NITE DSP motion engine V1

   A deliberately small interaction layer:
   - ONE shared window pointer listener + ONE shared requestAnimationFrame
     loop for every cursor-reactive surface on the page.
   - Subscribers write transforms / CSS custom properties directly to DOM
     refs. React state is never updated per frame.
   - The loop parks itself when there are no subscribers or the document is
     hidden (power management).
   - All rich pointer behaviour is gated behind (hover:hover) and
     (pointer:fine) and disabled under prefers-reduced-motion: reduce.
   ========================================================================== */

export function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/* --- Media capability hooks ------------------------------------------------ */

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, [query]);

  return matches;
}

/** True when the user prefers reduced motion (environmental motion off). */
export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}

/** True when a precise hover-capable pointer is the primary input. */
export function useFinePointer(): boolean {
  return useMediaQuery("(hover: hover) and (pointer: fine)");
}

/**
 * Combined gate for every cursor-reactive effect in the design language.
 * False during SSR and before hydration, so server HTML is always the calm,
 * static composition; effects attach only when appropriate.
 */
export function useReactivePointer(): boolean {
  const fine = useFinePointer();
  const reduced = useReducedMotion();
  return fine && !reduced;
}

/* --- Shared pointer signal -------------------------------------------------- */

export type PointerFrame = { x: number; y: number };

type PointerSubscriber = (frame: PointerFrame) => void;

const subscribers = new Set<PointerSubscriber>();
let latest: PointerFrame = { x: 0, y: 0 };
let rafId = 0;

function tick() {
  rafId = 0;
  for (const subscriber of subscribers) {
    subscriber(latest);
  }
  if (subscribers.size > 0) {
    rafId = requestAnimationFrame(tick);
  }
}

function ensureLoop() {
  if (rafId === 0 && subscribers.size > 0 && typeof document !== "undefined" && !document.hidden) {
    rafId = requestAnimationFrame(tick);
  }
}

function parkLoop() {
  if (rafId !== 0) {
    cancelAnimationFrame(rafId);
    rafId = 0;
  }
}

if (typeof window !== "undefined") {
  window.addEventListener(
    "pointermove",
    (event) => {
      latest = { x: event.clientX, y: event.clientY };
      ensureLoop();
    },
    { passive: true },
  );

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      parkLoop();
    } else {
      ensureLoop();
    }
  });
}

/**
 * Receive shared pointer frames inside the single global rAF loop.
 * Pass null to detach (e.g. when reduced-motion / coarse-pointer means the
 * surface must stay static). The callback must write only to refs/DOM —
 * never call setState per frame.
 */
export function usePointerSignal(subscriber: PointerSubscriber | null): void {
  useEffect(() => {
    if (!subscriber) return;
    subscribers.add(subscriber);
    ensureLoop();
    return () => {
      subscribers.delete(subscriber);
      if (subscribers.size === 0) parkLoop();
    };
  }, [subscriber]);
}
