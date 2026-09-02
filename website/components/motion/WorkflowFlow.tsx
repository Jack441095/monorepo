"use client";

import { useEffect, useRef } from "react";
import { clamp } from "@/lib/motion";

/* Signal-flow storytelling, the workflow list behaves like a processing
   chain: a blue→violet energy trace travels down the connector as the reader
   progresses, and each stage number activates when it crosses the reading
   line. Scroll-linked but rAF-throttled, passive, and static (full trace)
   under reduced motion. */

type WorkflowFlowProps = {
  steps: ReadonlyArray<readonly [string, string, string]>;
};

export function WorkflowFlow({ steps }: WorkflowFlowProps) {
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;

    const items = Array.from(list.querySelectorAll<HTMLElement>(".workflow-item"));
    let raf = 0;
    let queued = false;

    const update = () => {
      queued = false;
      const bounds = list.getBoundingClientRect();
      const readingLine = window.innerHeight * 0.58;
      const flow = clamp((readingLine - bounds.top) / bounds.height, 0.04, 1);
      list.style.setProperty("--flow", flow.toFixed(3));
      for (const item of items) {
        item.classList.toggle("is-active", item.getBoundingClientRect().top < readingLine);
      }
    };

    const onScroll = () => {
      if (!queued) {
        queued = true;
        raf = requestAnimationFrame(update);
      }
    };

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      // Reduced motion: the full trace is simply present; stage activation
      // still updates because state clarity is preserved.
      list.style.setProperty("--flow", "1");
    }

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
    <ol ref={listRef} className="workflow-list signal-track mt-12">
      {steps.map(([number, title, body]) => (
        <li key={number} className="workflow-item">
          <span className="workflow-number">{number}</span>
          <div>
            <h3 className="text-foreground">{title}</h3>
            <p>{body}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
