"use client";

import { FormEvent, useMemo, useState } from "react";

type ChatSource = {
  source?: string;
  title?: string;
  kind?: string;
  label?: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  confidence?: string;
  sources?: ChatSource[];
  outOfScope?: boolean;
};

type ChatResponse = {
  answer?: string;
  confidence?: string;
  intent?: string;
  sources?: ChatSource[];
};

const STARTERS = [
  "The kick disappears when the bass comes in.",
  "My vocal sounds harsh and thin.",
  "My wide mix collapses in mono.",
];

export function KennChatWidget() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const endpoint = process.env.NEXT_PUBLIC_KENN_CHAT_URL || "/kenn/chat";
  const evalUrl = process.env.NEXT_PUBLIC_KENN_EVAL_URL;
  const history = useMemo(
    () => messages.slice(-4).map(({ role, content }) => ({ role, content })),
    [messages],
  );

  async function submit(nextQuestion: string) {
    const cleanQuestion = nextQuestion.trim();
    if (!cleanQuestion || loading) return;

    setQuestion("");
    setError("");
    setLoading(true);
    setMessages((current) => [...current, { role: "user", content: cleanQuestion }]);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: cleanQuestion, history }),
      });
      const data = (await response.json().catch(() => ({}))) as ChatResponse;
      if (!response.ok) {
        throw new Error(`KENN chat returned ${response.status}.`);
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer || "KENN did not return an answer.",
          confidence: data.confidence,
          sources: data.sources || [],
          outOfScope: data.intent === "out_of_scope",
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "KENN could not be reached.");
      setMessages((current) => current.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit(question);
  }

  return (
    <div className="surface-card rounded-lg border border-border/50 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="eyebrow text-brand-violet-text">Retrieval demo</span>
          <h3 className="mt-3 text-xl font-semibold text-foreground">Ask a mix question.</h3>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            KENN answers from its approved local knowledge and shows the provenance metadata it used.
          </p>
        </div>
        {evalUrl ? (
          <a href={evalUrl} target="_blank" rel="noreferrer" className="btn-secondary text-xs">
            View evaluation receipt
          </a>
        ) : null}
      </div>

      <div className="mt-5 flex flex-wrap gap-2" aria-label="Starter questions">
        {STARTERS.map((starter) => (
          <button
            key={starter}
            type="button"
            onClick={() => void submit(starter)}
            disabled={loading}
            className="rounded-full border border-border-strong/60 px-3 py-1.5 text-left text-xs text-muted transition hover:border-brand-violet hover:text-foreground disabled:cursor-default disabled:opacity-50"
          >
            {starter}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-4" aria-live="polite">
        {messages.length === 0 ? (
          <p className="rounded-md border border-dashed border-border/60 p-4 text-sm text-muted-dim">
            Try a symptom such as “the kick disappears when the bass comes in”.
          </p>
        ) : null}
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`rounded-md border p-4 ${
              message.role === "user"
                ? "ml-6 border-border/50 bg-surface-raised/40"
                : message.outOfScope
                  ? "mr-6 border-[color:var(--state-warning-border)] bg-[color:var(--state-warning)]/5"
                  : "mr-6 border-brand-violet/30 bg-surface"
            }`}
          >
            <div className="flex items-center justify-between gap-3 text-[10px] font-mono uppercase tracking-wider text-muted-dim">
              <span>{message.role === "user" ? "You" : "KENN"}</span>
              {message.confidence ? <span>Confidence: {message.confidence}</span> : null}
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {message.content}
            </p>
            {message.role === "assistant" && message.sources && message.sources.length > 0 ? (
              <div className="mt-4 border-t border-border/40 pt-3">
                <p className="text-[10px] font-mono uppercase tracking-wider text-muted-dim">Sources</p>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {message.sources.map((source, sourceIndex) => (
                    <li key={`${source.source || source.title || "source"}-${sourceIndex}`}>
                      {source.label || source.title || source.source || "Approved KENN source"}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ))}
        {loading ? <p className="text-xs font-mono text-muted-dim">KENN is checking approved sources…</p> : null}
      </div>

      {error ? <p className="mt-4 text-sm text-[color:var(--state-warning)]">{error}</p> : null}

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3 sm:flex-row">
        <label htmlFor="kenn-chat-question" className="sr-only">
          Mix question
        </label>
        <input
          id="kenn-chat-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={1200}
          placeholder="Ask about a mix symptom…"
          className="min-w-0 flex-1 rounded-md border border-border-strong/70 bg-surface-raised px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-dim focus:border-brand-violet"
        />
        <button type="submit" disabled={loading || !question.trim()} className="btn-primary disabled:cursor-default disabled:opacity-50">
          Ask KENN
        </button>
      </form>
      <p className="mt-4 text-xs leading-relaxed text-muted-dim">
        Retrieval-only and tested against KENN&rsquo;s held-out evaluation harness. No audio is uploaded,
        measured, or analysed by this chat; out-of-scope questions are refused.
      </p>
    </div>
  );
}
