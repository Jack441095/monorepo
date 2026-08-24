"use client";

import { useCallback, type ReactNode } from "react";
import { clamp, useReactivePointer } from "@/lib/motion";

/* DEPTH 3 — Restrained magnetic control.
   The semantic control (link/button) keeps a perfectly stationary hit area;
   only this inner content span is translated toward the pointer by at most
   ~3px. Smoothing is handled entirely by CSS transitions: a fast linear
   follow while engaged, a soft spring-like return on leave. No JS animation
   loop runs. Renders identical DOM regardless of capability so hydration
   stays deterministic. Reserved for flagship CTAs — never every button. */

type MagneticProps = {
  children: ReactNode;
  /** Maximum displacement in px (design ceiling 4). */
  max?: number;
};

export function Magnetic({ children, max = 3 }: MagneticProps) {
  const reactive = useReactivePointer();

  const onPointerEnter = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      if (!reactive) return;
      event.currentTarget.classList.add("magnetic--engaged");
    },
    [reactive],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      if (!reactive) return;
      const el = event.currentTarget;
      if (!el.classList.contains("magnetic--engaged")) return;
      const bounds = el.getBoundingClientRect();
      const nx = clamp((event.clientX - bounds.left) / bounds.width - 0.5, -0.5, 0.5);
      const ny = clamp((event.clientY - bounds.top) / bounds.height - 0.5, -0.5, 0.5);
      // Vertical response is damped — horizontal pull reads as intent,
      // vertical pull reads as wobble.
      el.style.setProperty("--mag-x", `${(nx * 2 * max).toFixed(2)}px`);
      el.style.setProperty("--mag-y", `${(ny * 2 * max * 0.7).toFixed(2)}px`);
    },
    [reactive, max],
  );

  const onPointerLeave = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      if (!reactive) return;
      const el = event.currentTarget;
      el.classList.remove("magnetic--engaged");
      el.style.setProperty("--mag-x", "0px");
      el.style.setProperty("--mag-y", "0px");
    },
    [reactive],
  );

  return (
    <span
      className="magnetic__content"
      onPointerEnter={onPointerEnter}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      {children}
    </span>
  );
}
