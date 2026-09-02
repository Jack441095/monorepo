"use client";

import { useEffect, useRef } from "react";
import { clamp } from "@/lib/motion";

/* The NITE Signal Journey, homepage company-level signal flow.

   DISCOVER → ANALYSE → UNDERSTAND → CREATE

   The connector fills with brand energy (blue → violet → red) as the reader
   progresses, and each node activates at the viewport reading line. Same
   scroll contract as WorkflowFlow: passive listeners, rAF-throttled, static
   full trace under reduced motion (node activation is state, kept). */

const STAGES = [
  {
    stage: "DISCOVER",
    title: "Signal enters the system.",
    body: "Raw material, sample libraries, documents, mixes, stays exactly where it is. Nothing is uploaded to understand it.",
  },
  {
    stage: "ANALYSE",
    title: "Local DSP reads the signal.",
    body: "NITE DSP tools analyse the content itself: transients, spectra, structure, on your machine, in real time.",
  },
  {
    stage: "UNDERSTAND",
    title: "Patterns become intelligence.",
    body: "Analysis becomes usable knowledge: what a sound is, what a document needs, where a mix could improve.",
  },
  {
    stage: "CREATE",
    title: "You act with confidence.",
    body: "Intelligence stays assistive. Recommendations come to you, the creative decisions remain yours.",
  },
] as const;

export function SignalJourney() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const nodes = Array.from(root.querySelectorAll<HTMLElement>(".journey__node"));
    let raf = 0;
    let queued = false;

    const update = () => {
      queued = false;
      const bounds = root.getBoundingClientRect();
      const readingLine = window.innerHeight * 0.62;
      const flow = clamp((readingLine - bounds.top) / bounds.height, 0.06, 1);
      root.style.setProperty("--flow", flow.toFixed(3));
      for (const node of nodes) {
        const marker = node.querySelector<HTMLElement>(".journey__marker");
        if (!marker) continue;
        const markerY = marker.getBoundingClientRect().top;
        node.classList.toggle("is-active", markerY < readingLine);
      }
    };

    const onScroll = () => {
      if (!queued) {
        queued = true;
        raf = requestAnimationFrame(update);
      }
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <section className="section section-rule">
      <div className="site-container">
        <div className="max-w-2xl">
          <span className="eyebrow">The NITE Signal Journey</span>
          <h2 className="section-title mt-4">From raw signal to creative confidence.</h2>
          <p className="mt-5 text-base leading-relaxed" style={{ color: "var(--muted)" }}>
            Every NITE DSP tool walks the same path, and your material never
            has to leave your machine to walk it.
          </p>
        </div>

        <div ref={rootRef} className="journey mt-14" style={{ ["--flow" as string]: "0.06" }}>
          <div className="journey__track" aria-hidden="true" />
          <div className="journey__fill" aria-hidden="true" />
          <div className="journey__grid">
            {STAGES.map(({ stage, title, body }) => (
              <div key={stage} className="journey__node">
                <span className="journey__marker" aria-hidden="true" />
                <div>
                  <span className="journey__stage">{stage}</span>
                  <h3 className="text-foreground">{title}</h3>
                  <p>{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
