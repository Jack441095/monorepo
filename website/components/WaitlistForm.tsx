"use client";

import { useEffect, useState } from "react";
import { apiFetch, API_URL } from "@/lib/api";

interface QualifyingQuestion {
  id: string;
  label: string;
  placeholder: string;
  options?: string[];
}

const QUALIFYING_QUESTIONS: Record<string, QualifyingQuestion[]> = {
  "smart-sample-manager": [
    {
      id: "library_size",
      label: "How large is your sample library?",
      placeholder: "",
      options: ["Under 5,000 samples", "5,000–20,000", "20,000–100,000", "100,000+"],
    },
    {
      id: "daw",
      label: "Primary DAW",
      placeholder: "",
      options: ["Ableton Live", "Logic Pro", "FL Studio", "Pro Tools", "Other"],
    },
  ],
  submit: [
    {
      id: "doc_volume",
      label: "How many documents do you prepare per month?",
      placeholder: "",
      options: ["1–5", "5–15", "15–50", "50+"],
    },
    {
      id: "doc_type",
      label: "What type of documents?",
      placeholder: "",
      options: ["Academic / coursework", "Professional / business", "Creative / portfolio", "Mixed"],
    },
  ],
  kenn: [
    {
      id: "daw",
      label: "Primary DAW",
      placeholder: "",
      options: ["Ableton Live", "Logic Pro", "FL Studio", "Pro Tools", "Other"],
    },
    {
      id: "experience",
      label: "How would you describe your mixing experience?",
      placeholder: "",
      options: ["Just starting out", "A few years in", "Experienced", "Professional engineer"],
    },
  ],
};

interface Props {
  productId: string;
  capacity?: number;
}

export function WaitlistForm({ productId, capacity: defaultCapacity = 50 }: Props) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [useCase, setUseCase] = useState("");
  const [qualifiers, setQualifiers] = useState<Record<string, string>>({});
  const [count, setCount] = useState<number | null>(null);
  const [capacity, setCapacity] = useState(defaultCapacity);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/waitlist/count/${productId}`)
      .then((r) => r.json())
      .then((data) => {
        setCount(data.count);
        setCapacity(data.capacity);
      })
      .catch(() => {});
  }, [productId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const qualifierSummary = Object.entries(qualifiers)
        .filter(([, v]) => v)
        .map(([k, v]) => `${k}: ${v}`)
        .join("; ");
      const fullUseCase = [qualifierSummary, useCase].filter(Boolean).join(" | ") || null;

      const res = await apiFetch("/waitlist/join", {
        method: "POST",
        body: JSON.stringify({
          email,
          name: name || null,
          product_id: productId,
          use_case: fullUseCase,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? "Something went wrong. Please try again.");
        setBusy(false);
        return;
      }
      const data = await res.json();
      setCount(data.count);
      setCapacity(data.capacity);
      setSubmitted(true);
    } catch {
      setError("Could not reach our server. Please try again.");
    }
    setBusy(false);
  }

  const spotsLeft = count !== null ? Math.max(0, capacity - count) : null;
  const pct = count !== null ? Math.min(100, Math.round((count / capacity) * 100)) : 0;

  if (submitted) {
    return (
      <div className="surface-card p-8 border border-brand-blue/30 rounded-lg text-center">
        <h2 className="text-lg font-semibold text-foreground">You&apos;re on the list.</h2>
        <p className="mt-3 text-sm text-muted leading-relaxed">
          We&apos;ll email you when your spot opens up. In the meantime, your place is secured.
        </p>
        {count !== null && (
          <p className="mt-4 font-mono text-xs text-muted-dim">
            {count} of {capacity} spots claimed
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="surface-card p-8 border border-border/40 rounded-lg">
      {count !== null && (
        <div className="mb-6">
          <div className="flex justify-between items-baseline mb-2">
            <span className="font-mono text-sm font-semibold text-foreground">
              {count} of {capacity} spots claimed
            </span>
            {spotsLeft !== null && spotsLeft > 0 && spotsLeft <= 15 && (
              <span className="text-xs font-semibold" style={{ color: "var(--state-error, #dc2626)" }}>
                {spotsLeft} left
              </span>
            )}
          </div>
          <div
            className="w-full h-2 rounded-full overflow-hidden"
            style={{ background: "var(--border)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${pct}%`,
                background: pct >= 90 ? "var(--state-error, #dc2626)" : "var(--brand-blue-bright, #2563eb)",
              }}
            />
          </div>
        </div>
      )}

      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="wl-email" className="u-label block mb-2">
            Email
          </label>
          <input
            id="wl-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-md border px-3 py-2 text-sm bg-transparent text-foreground"
            style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
          />
        </div>
        <div>
          <label htmlFor="wl-name" className="u-label block mb-2">
            Name <span className="text-muted-dim">(optional)</span>
          </label>
          <input
            id="wl-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm bg-transparent text-foreground"
            style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
          />
        </div>
        {(QUALIFYING_QUESTIONS[productId] ?? []).map((q) => (
          <div key={q.id}>
            <label htmlFor={`wl-${q.id}`} className="u-label block mb-2">
              {q.label}
            </label>
            {q.options ? (
              <select
                id={`wl-${q.id}`}
                value={qualifiers[q.id] ?? ""}
                onChange={(e) => setQualifiers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                className="w-full rounded-md border px-3 py-2 text-sm bg-transparent"
                style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
              >
                <option value="">Select…</option>
                {q.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <input
                id={`wl-${q.id}`}
                value={qualifiers[q.id] ?? ""}
                onChange={(e) => setQualifiers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                placeholder={q.placeholder}
                className="w-full rounded-md border px-3 py-2 text-sm bg-transparent"
                style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
              />
            )}
          </div>
        ))}
        <div>
          <label htmlFor="wl-usecase" className="u-label block mb-2">
            Anything else we should know? <span className="text-muted-dim">(optional)</span>
          </label>
          <textarea
            id="wl-usecase"
            rows={2}
            value={useCase}
            onChange={(e) => setUseCase(e.target.value)}
            placeholder={productId === "smart-sample-manager"
              ? "e.g. I have 40,000 samples across 200 folders and can never find the right kick."
              : "e.g. I prepare coursework submissions weekly and always worry about naming errors."}
            className="w-full rounded-md border px-3 py-2 text-sm bg-transparent"
            style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
          />
        </div>
        <p className="text-xs text-muted-dim leading-relaxed">
          Your email is stored securely and used only to notify you when your spot opens.
          We never share it. See our{" "}
          <a href="/privacy" className="text-link">
            privacy policy
          </a>.
        </p>
        {error && (
          <p role="alert" className="text-xs" style={{ color: "var(--state-error, #dc2626)" }}>
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary self-start" disabled={busy}>
          {busy ? "Joining…" : "Claim your spot"}
        </button>
      </form>
    </div>
  );
}

export function WaitlistCounter({ productId }: { productId: string }) {
  const [count, setCount] = useState<number | null>(null);
  const [capacity, setCapacity] = useState(50);

  useEffect(() => {
    fetch(`${API_URL}/waitlist/count/${productId}`)
      .then((r) => r.json())
      .then((data) => {
        setCount(data.count);
        setCapacity(data.capacity);
      })
      .catch(() => {});
  }, [productId]);

  if (count === null) return null;

  return (
    <span className="font-mono text-xs text-muted-dim">
      {count} of {capacity} beta spots claimed
    </span>
  );
}
