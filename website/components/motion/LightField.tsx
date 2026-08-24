"use client";

import { useCallback, useRef } from "react";
import { clamp, lerp, usePointerSignal, useReactivePointer } from "@/lib/motion";

/* DEPTH 1 — Ambient cursor-reactive studio lighting.
   Two diffuse energy fields (blue input, violet processing) drift 10–30 px
   around their authored resting positions with delayed inertia; a very dim
   red transient field trails furthest behind. This reads as moving studio
   illumination, never a cursor flashlight. Static fallback whenever rich
   pointer input is unavailable. */

const BLOB_RATES = [0.06, 0.035, 0.02] as const;
const BLOB_RANGE_X = [26, 34, 42] as const;
const BLOB_RANGE_Y = [16, 22, 26] as const;

export function LightField() {
  const containerRef = useRef<HTMLDivElement>(null);
  const blobRefs = useRef<Array<HTMLDivElement | null>>([]);
  const current = useRef([
    { x: 0, y: 0 },
    { x: 0, y: 0 },
    { x: 0, y: 0 },
  ]);

  const reactive = useReactivePointer();

  const subscriber = useCallback(
    (frame: { x: number; y: number }) => {
      const container = containerRef.current;
      if (!container) return;
      const bounds = container.getBoundingClientRect();
      if (bounds.bottom < -80 || bounds.top > window.innerHeight + 80) return;

      const nx = clamp(frame.x / window.innerWidth - 0.5, -0.6, 0.6) * 2;
      const ny = clamp(frame.y / window.innerHeight - 0.5, -0.6, 0.6) * 2;

      blobRefs.current.forEach((blob, i) => {
        if (!blob) return;
        const state = current.current[i];
        const tx = nx * BLOB_RANGE_X[i];
        const ty = ny * BLOB_RANGE_Y[i];
        state.x = lerp(state.x, tx, BLOB_RATES[i]);
        state.y = lerp(state.y, ty, BLOB_RATES[i]);
        blob.style.transform = `translate3d(${state.x.toFixed(2)}px, ${state.y.toFixed(2)}px, 0)`;
      });
    },
    [],
  );

  usePointerSignal(reactive ? subscriber : null);

  return (
    <div ref={containerRef} className="light-field" aria-hidden="true">
      {(["blue", "violet", "red"] as const).map((tone, i) => (
        <div
          key={tone}
          ref={(el) => {
            blobRefs.current[i] = el;
          }}
          className={`light-field__blob light-field__blob--${tone}`}
        />
      ))}
    </div>
  );
}
