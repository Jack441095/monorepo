"use client";

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { clamp, useReactivePointer } from "@/lib/motion";

/* DEPTH 2 — Micro-3D hardware frame.
   Wraps a premium surface (screenshot frame, flagship card) in a perspective
   container. Pointer movement produces <= 1.6deg tilt, a pointer-tracking
   border bloom, an interior sheen shift, and optional per-layer parallax for
   children marked data-depth="n" (px, sign controls direction). The result
   should feel like looking at a physical studio device — never like a
   floating 3D card demo. Static and fully readable when disabled. */

type TiltSurfaceProps = {
  children: ReactNode;
  className?: string;
  radius?: string;
  maxTiltDeg?: number;
};

export function TiltSurface({
  children,
  className,
  radius = "var(--radius-lg)",
  maxTiltDeg = 1.6,
}: TiltSurfaceProps) {
  const innerRef = useRef<HTMLDivElement>(null);
  const reactive = useReactivePointer();

  const setVar = useCallback((name: string, value: string) => {
    innerRef.current?.style.setProperty(name, value);
  }, []);

  const applyLayerDepths = useCallback(() => {
    const inner = innerRef.current;
    if (!inner) return;
    inner.querySelectorAll<HTMLElement>("[data-depth]").forEach((layer) => {
      layer.style.setProperty("--layer-depth", layer.dataset.depth ?? "0");
      layer.classList.add("tilt-surface__layer");
    });
  }, []);

  useEffect(() => {
    if (reactive) applyLayerDepths();
  }, [reactive, applyLayerDepths]);

  const onPointerEnter = useCallback(() => {
    if (!reactive) return;
    innerRef.current?.classList.add("is-engaged");
  }, [reactive]);

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!reactive) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      const nx = clamp((event.clientX - bounds.left) / bounds.width - 0.5, -0.5, 0.5) * 2;
      const ny = clamp((event.clientY - bounds.top) / bounds.height - 0.5, -0.5, 0.5) * 2;
      setVar("--tilt-y", `${(nx * maxTiltDeg).toFixed(2)}deg`);
      setVar("--tilt-x", `${(-ny * maxTiltDeg).toFixed(2)}deg`);
      setVar("--glow-x", `${(((event.clientX - bounds.left) / bounds.width) * 100).toFixed(1)}%`);
      setVar("--glow-y", `${(((event.clientY - bounds.top) / bounds.height) * 100).toFixed(1)}%`);
      setVar("--par-x", nx.toFixed(3));
      setVar("--par-y", ny.toFixed(3));
    },
    [reactive, maxTiltDeg, setVar],
  );

  const onPointerLeave = useCallback(() => {
    if (!reactive) return;
    const inner = innerRef.current;
    if (!inner) return;
    inner.classList.remove("is-engaged");
    setVar("--tilt-x", "0deg");
    setVar("--tilt-y", "0deg");
    setVar("--par-x", "0");
    setVar("--par-y", "0");
  }, [reactive, setVar]);

  return (
    <div
      className={`tilt-surface ${className ?? ""}`}
      style={{ borderRadius: radius }}
      onPointerEnter={onPointerEnter}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <div ref={innerRef} className="tilt-surface__inner" style={{ borderRadius: radius }}>
        <span className="tilt-surface__bloom" aria-hidden="true" style={{ borderRadius: radius }} />
        {children}
        <span className="tilt-surface__sheen" aria-hidden="true" style={{ borderRadius: radius }} />
      </div>
    </div>
  );
}
