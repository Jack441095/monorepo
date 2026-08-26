"use client";

import { useState } from "react";

/**
 * Beta / notify request capture. There is intentionally no new backend
 * endpoint: requests are composed into an email to the existing support
 * address (nitedsp@outlook.com). Nothing is uploaded anywhere by this form.
 */
export function BetaRequestForm({ intent }: { intent?: string }) {
  const [name, setName] = useState("");
  const [useCase, setUseCase] = useState(intent === "notify" ? "Notify me when SLO or KENN opens up." : "");
  const [opened, setOpened] = useState(false);

  const subject = intent === "notify" ? "NITE DSP beta notify request" : "NITE Submit beta access request";
  const body = encodeURIComponent(
    `Name: ${name}\n\nWhat I'd like to do with NITE software:\n${useCase}\n\nmacOS version:\n`,
  );

  if (opened) {
    return (
      <div className="surface-card p-8 border border-brand-blue/30 rounded-lg text-center">
        <h2 className="text-lg font-semibold text-foreground">Your email app should be opening.</h2>
        <p className="mt-3 text-sm text-muted leading-relaxed">
          We review requests manually and reply from{" "}
          <span className="font-mono text-xs">nitedsp@outlook.com</span>. If your mail client
          didn&apos;t open, send the details to that address directly.
        </p>
        <a
          href={`mailto:nitedsp@outlook.com?subject=${encodeURIComponent(subject)}&body=${body}`}
          className="btn-primary mt-6 inline-block"
        >
          Open email again
        </a>
      </div>
    );
  }

  return (
    <form
      className="surface-card p-8 border border-border/40 rounded-lg flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        setOpened(true);
      }}
    >
      <div>
        <label htmlFor="beta-name" className="u-label block mb-2">
          Name
        </label>
        <input
          id="beta-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border px-3 py-2 text-sm bg-transparent text-foreground"
          style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
        />
      </div>
      <div>
        <label htmlFor="beta-usecase" className="u-label block mb-2">
          What would you like to do?
        </label>
        <textarea
          id="beta-usecase"
          required
          rows={4}
          value={useCase}
          onChange={(e) => setUseCase(e.target.value)}
          placeholder="e.g. Prepare my dissertation PDF before submitting it to my department."
          className="w-full rounded-md border px-3 py-2 text-sm bg-transparent"
          style={{ borderColor: "var(--border-strong)", color: "var(--foreground)" }}
        />
      </div>
      <p className="text-xs text-muted-dim leading-relaxed">
        This form does not upload anything. It opens an email draft in your own mail app so your
        details stay on your machine until you choose to send them.
      </p>
      <button type="submit" className="btn-primary self-start">
        Continue to email draft
      </button>
    </form>
  );
}
