import type { ReactNode } from "react";

/* ============================================================================
   Intelligence UI — the explainable-intelligence component vocabulary.

   Rule: intelligence is never magic. Every intelligent claim is paired with
   evidence, a confidence level (glyph + text, never colour-only), and an
   explanation. These components are the only sanctioned way to present
   machine-derived findings on NITE DSP surfaces.
   ========================================================================== */

export type Confidence = "high" | "medium" | "low" | "unknown";

const CONFIDENCE_META: Record<Confidence, { label: string; glyph: string; color: string }> = {
  high: { label: "High confidence", glyph: "●●", color: "var(--confidence-high)" },
  medium: { label: "Medium confidence", glyph: "●○", color: "var(--confidence-medium)" },
  low: { label: "Low confidence", glyph: "○○", color: "var(--confidence-low)" },
  unknown: { label: "Unknown", glyph: "?", color: "var(--confidence-unknown)" },
};

export function ConfidenceBadge({ level, hint }: { level: Confidence; hint?: string }) {
  const meta = CONFIDENCE_META[level];
  return (
    <span
      className="chip"
      title={hint ?? meta.label}
      style={{ borderColor: meta.color, color: meta.color }}
    >
      <span aria-hidden="true" className="tracking-normal">{meta.glyph}</span>
      {meta.label}
    </span>
  );
}

/* EvidenceCard — one machine finding: what was detected, the signal that
   produced it, and how confident the system is. */
export function EvidenceCard({
  finding,
  signal,
  confidence,
  children,
}: {
  finding: ReactNode;
  signal: string;
  confidence: Confidence;
  children?: ReactNode;
}) {
  return (
    <div className="panel panel--flat p-4 flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <span className="u-data text-foreground">{finding}</span>
        <ConfidenceBadge level={confidence} />
      </div>
      <p className="u-meta">
        <span style={{ color: "var(--brand-blue-bright)" }}>signal ·</span> {signal}
      </p>
      {children && <div className="u-body text-[13px]">{children}</div>}
    </div>
  );
}

/* ReasoningPanel — "we detected this because these signals were found."
   The canonical anti-magic component. */
export function ReasoningPanel({
  title = "Why this result",
  reasons,
}: {
  title?: string;
  reasons: ReadonlyArray<{ signal: string; explanation: string }>;
}) {
  return (
    <div className="panel panel--flat p-4">
      <p className="u-label" style={{ color: "var(--muted-dim)" }}>{title}</p>
      <ul className="mt-3 flex flex-col gap-2.5">
        {reasons.map((r) => (
          <li key={r.signal} className="flex items-start gap-2.5 text-[13px] leading-relaxed">
            <span aria-hidden="true" className="flex-none mt-0.5 u-meta" style={{ color: "var(--brand-blue-bright)" }}>
              signal
            </span>
            <span className="min-w-0">
              <span className="u-data text-foreground">{r.signal}</span>
              <span className="u-body text-[13px]"> — {r.explanation}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ApprovalGate — non-destructive by default: the human decides. */
export function ApprovalGate({
  action,
  note,
  state = "awaiting",
}: {
  action: string;
  note?: string;
  state?: "awaiting" | "approved";
}) {
  return (
    <div
      className="panel panel--flat p-4 flex items-center justify-between gap-3"
      style={{ borderColor: state === "approved" ? "rgba(16,185,129,0.35)" : "var(--state-warning-border)" }}
    >
      <div className="min-w-0">
        <p className="u-data text-foreground">{action}</p>
        {note && <p className="u-meta mt-1">{note}</p>}
      </div>
      {state === "approved" ? (
        <span className="chip chip--success flex-none">
          <span aria-hidden="true" className="dsp-led dsp-led--green" /> Approved
        </span>
      ) : (
        <span className="chip chip--warn flex-none">
          <span aria-hidden="true" className="dsp-led dsp-led--amber" /> Awaiting approval
        </span>
      )}
    </div>
  );
}

/* AgentStatus — for orchestration surfaces. States are honest: an agent is
   never "thinking" unless it is actually running; approval is explicit. */
export type AgentState = "queued" | "running" | "awaiting-approval" | "done" | "failed";

const AGENT_META: Record<AgentState, { label: string; ledClass: string; color: string; pulse: boolean }> = {
  queued: { label: "Queued", ledClass: "dsp-led", color: "var(--agent-idle)", pulse: false },
  running: { label: "Running", ledClass: "dsp-led dsp-led--live", color: "var(--agent-running)", pulse: true },
  "awaiting-approval": { label: "Awaiting approval", ledClass: "dsp-led dsp-led--amber", color: "var(--agent-approval)", pulse: false },
  done: { label: "Done", ledClass: "dsp-led dsp-led--green", color: "var(--agent-done)", pulse: false },
  failed: { label: "Needs attention", ledClass: "dsp-led dsp-led--red", color: "var(--agent-failed)", pulse: false },
};

export function AgentStatus({ state, label }: { state: AgentState; label: string }) {
  const meta = AGENT_META[state];
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-edge last:border-b-0 font-sans">
      <span className="u-body text-[13px] text-foreground min-w-0">{label}</span>
      <span
        className={`chip flex-none`}
        style={{ borderColor: meta.color, color: meta.color }}
      >
        <span aria-hidden="true" className={meta.ledClass} />
        {meta.label}
      </span>
    </div>
  );
}
