"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  FREE_DAILY_LIMIT,
  VOICES,
  ParaphraseError,
  readUsage,
  recordUsage,
  requestParaphrase,
  unlockParaphrase,
  type Voice,
} from "@/lib/paraphrase";

type Status = "idle" | "streaming" | "done" | "error" | "rate-limited";

const VOICE_LABELS: Record<Voice, string> = {
  essay: "Essay",
  email: "Email",
  report: "Report",
  casual: "Casual",
};

const TIER_BUTTONS = [
  { id: "gbp-1" as const, label: "£1", subtitle: "Just because" },
  { id: "gbp-3" as const, label: "£3", subtitle: "Fair trade" },
  { id: "gbp-10" as const, label: "£10", subtitle: "Thanks a lot" },
];

export function ParaphraseBox() {
  const [voice, setVoice] = useState<Voice>("essay");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [alerts, setAlerts] = useState<string[]>([]);
  const [stats, setStats] = useState<{ tokens?: number; seconds?: number }>({});
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [showPaywall, setShowPaywall] = useState(false);
  const [unlockMessage, setUnlockMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const usage = readUsage();
  const remaining = Math.max(0, FREE_DAILY_LIMIT - usage.used);
  const charCount = input.length;

  const disabled = status === "streaming";

  const reset = useCallback(() => {
    setOutput("");
    setAlerts([]);
    setStats({});
    setError("");
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || !input.trim()) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    reset();
    setStatus("streaming");

    const pendingOutput: string[] = [];
    try {
      for await (const event of requestParaphrase(voice, input, controller.signal)) {
        if (controller.signal.aborted) return;
        if (event.type === "token") {
          pendingOutput.push(event.token);
          setOutput(pendingOutput.join(""));
        } else if (event.type === "alert") {
          setAlerts((prev) => [...prev, event.message]);
        } else if (event.type === "error") {
          throw new ParaphraseError(0, event.message);
        } else if (event.type === "done") {
          setStats(event.stats ?? {});
          recordUsage();
        }
      }
      if (controller.signal.aborted) return;
      setOutput(pendingOutput.join(""));
      setStatus("done");
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      if (caught instanceof ParaphraseError) {
        if (caught.status === 429) {
          setError("");
          setStatus("rate-limited");
          setShowPaywall(true);
          return;
        }
        setError(caught.message);
      } else {
        setError("Could not reach the paraphrase service.");
      }
      setStatus("error");
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    setStatus("idle");
  }

  async function onSelectTier(id: "gbp-1" | "gbp-3" | "gbp-10") {
    const result = await unlockParaphrase(id);
    if (result.ok) {
      setUnlockMessage("Unlimited rewrites unlocked for today.");
      setShowPaywall(false);
    } else {
      setUnlockMessage(result.error);
    }
  }

  return (
    <div className="surface-card rounded-lg border border-border/50 p-5 sm:p-6">
      {/* Positioning banner */}
      <div className="mb-5 rounded-md border border-border/50 bg-surface/60 px-4 py-2 text-[11px] font-mono leading-relaxed text-muted-dim">
        Rewrites your text so it sounds natural. A drafting aid, not a substitute for
        your own thinking.
      </div>

      {/* Voice + textarea */}
      <form onSubmit={onSubmit}>
        <div className="flex flex-wrap gap-2" aria-label="Rewrite voice">
          {VOICES.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => {
                setVoice(v);
                reset();
              }}
              className={`rounded-full border px-3 py-1.5 text-[11px] font-mono uppercase tracking-wider transition ${
                voice === v
                  ? "border-brand-violet bg-brand-violet/10 text-foreground"
                  : "border-border-strong/60 text-muted hover:border-brand-violet hover:text-foreground"
              }`}
            >
              {VOICE_LABELS[v]}
            </button>
          ))}
        </div>

        <label htmlFor="paraphrase-input" className="sr-only">
          Text to rewrite
        </label>
        <textarea
          id="paraphrase-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={8000}
          rows={5}
          placeholder="Paste the text you want to rewrite…"
          className="mt-4 w-full resize-y rounded-md border border-border-strong/70 bg-surface-raised px-4 py-3 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-dim focus:border-brand-violet"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-muted-dim">
          <span>
            {remaining} of {FREE_DAILY_LIMIT} free rewrites today
            {unlockMessage ? ` — ${unlockMessage}` : null}
          </span>
          <span>{charCount.toLocaleString()}/8 000</span>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={disabled || !input.trim()}
            className="btn-primary disabled:cursor-default disabled:opacity-50"
          >
            Rewrite
          </button>
          {disabled ? (
            <button
              type="button"
              onClick={handleStop}
              className="btn-secondary"
            >
              Stop
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setShowPaywall(true)}
            className="text-xs font-mono text-muted-dim underline decoration-border/50 underline-offset-2 hover:text-foreground"
          >
            Support / Get unlimited
          </button>
        </div>
      </form>

      {/* Alerts */}
      {alerts.length > 0 ? (
        <div className="mt-6 space-y-2" aria-live="polite">
          {alerts.map((message, i) => (
            <div
              key={i}
              className="rounded-md border border-[color:var(--state-warning-border)] bg-[color:var(--state-warning)]/5 px-3 py-2 text-[11px] text-muted"
            >
              {message}
            </div>
          ))}
        </div>
      ) : null}

      {/* Output */}
      <div className="mt-6 space-y-3">
        {output ? (
          <div
            className="rounded-md border border-border/50 bg-surface px-4 py-3 text-sm leading-relaxed text-foreground"
            aria-live="polite"
          >
            {output}
            {status === "streaming" ? (
              <span className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-foreground" />
            ) : null}
          </div>
        ) : null}

        {status === "error" && error ? (
          <p className="mt-2 text-sm text-[color:var(--state-warning)]">{error}</p>
        ) : null}

        {status === "done" && stats.seconds != null ? (
          <p className="mt-2 text-[11px] font-mono text-muted-dim">
            Rewritten {stats.tokens ?? 0} tokens in {stats.seconds.toFixed(1)}s
          </p>
        ) : null}
      </div>

      {/* Paywall modal */}
      {showPaywall ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="paywall-title"
        >
          <div className="surface-card w-full max-w-sm rounded-lg border border-border/60 p-6 shadow-lg">
            <h3 id="paywall-title" className="text-base font-semibold text-foreground">
              Pay what you like
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Free rewrites reset each day. Pay once to remove the limit for this
              session — any amount feels right.
            </p>
            <div className="mt-6 grid grid-cols-3 gap-3">
              {TIER_BUTTONS.map((tier) => (
                <button
                  key={tier.id}
                  onClick={() => void onSelectTier(tier.id)}
                  className="flex flex-col items-center gap-1 rounded-md border border-border-strong/60 px-3 py-3 text-center transition hover:border-brand-violet hover:bg-brand-violet/5"
                >
                  <span className="text-lg font-semibold text-foreground">{tier.label}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted-dim">
                    {tier.subtitle}
                  </span>
                </button>
              ))}
            </div>
            {unlockMessage ? (
              <p className="mt-4 text-center text-xs text-muted-dim">{unlockMessage}</p>
            ) : null}
            <button
              onClick={() => setShowPaywall(false)}
              className="mt-5 w-full rounded-md border border-border/50 px-3 py-2 text-center text-xs text-muted transition hover:text-foreground"
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}