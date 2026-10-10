"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  FREE_DAILY_LIMIT,
  VOICES,
  ParaphraseError,
  readUsage,
  recordUsage,
  requestParaphrase,
  type Voice,
} from "@/lib/paraphrase";

type Status = "idle" | "streaming" | "done" | "error" | "rate-limited";

const VOICE_LABELS: Record<Voice, string> = {
  essay: "Essay",
  email: "Email",
  report: "Report",
  casual: "Casual",
};

export function ParaphraseBox() {
  const [voice, setVoice] = useState<Voice>("essay");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [alerts, setAlerts] = useState<string[]>([]);
  const [stats, setStats] = useState<{ tokens?: number; seconds?: number }>({});
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
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
          // A daily cap keeps the free service available; it no longer offers a paid bypass.
          setError("Para-phase is free. The daily limit has been reached; please try again tomorrow.");
          setStatus("rate-limited");
          return;
        }
        setError(caught.message);
      } else {
        setError("Could not reach Para-phase.");
      }
      setStatus("error");
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    setStatus("idle");
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

        {(status === "error" || status === "rate-limited") && error ? (
          <p className="mt-2 text-sm text-[color:var(--state-warning)]">{error}</p>
        ) : null}

        {status === "done" && stats.seconds != null ? (
          <p className="mt-2 text-[11px] font-mono text-muted-dim">
            Rewritten {stats.tokens ?? 0} tokens in {stats.seconds.toFixed(1)}s
          </p>
        ) : null}
      </div>

    </div>
  );
}