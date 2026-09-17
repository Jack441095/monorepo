"use client";

import { useState } from "react";

const SLIDES = [
  {
    eyebrow: "NITE DSP",
    title: "Intelligent tools for creative workflows",
    body: "Local-first macOS software for producers and students.\nYour files never leave your machine.",
    accent: "var(--brand-blue-bright)",
  },
  {
    eyebrow: "The Problem",
    title: "The gap between 'done' and 'submitted'",
    body: "Students lose marks because of filenames, metadata, and formatting. Not because of their work.\n\nThe tools that exist check grammar or catch plagiarism. Nothing checks the structural stuff.",
    accent: "var(--state-error, #dc2626)",
  },
  {
    eyebrow: "Submit",
    title: "Prepare the right submission",
    body: "Drop in a file. Submit checks the filename format, PDF metadata, anonymisation, and structure.\n\nIt makes a safe copy with corrections. It never modifies your original. It never reads your content.\n\nLocal macOS app. No upload. No account. £3 perpetual licence.",
    accent: "var(--state-success, #16a34a)",
  },
  {
    eyebrow: "Live Demo",
    title: "Submit in 30 seconds",
    body: "1. Drop a PDF into Submit\n2. Review the detected checks (filename, metadata, page count)\n3. Approve or adjust\n4. Save the prepared copy + verification receipt\n\n[Run the live demo here]",
    accent: "var(--brand-blue-bright)",
  },
  {
    eyebrow: "SLO",
    title: "Find sounds by how they sound",
    body: "40,000 samples. Hundreds of folders. Filenames like XK29_0047.wav.\n\nSLO analyses the acoustic signal and lets you search by timbre, not tags.\nDrag matches straight into Ableton Live or any DAW.\n\n100% offline. No subscription. £29 perpetual licence.",
    accent: "var(--brand-blue-bright)",
  },
  {
    eyebrow: "KENN",
    title: "Your AI audio assistant for Ableton",
    body: "KENN listens to your mix and explains what it hears.\n\nIt shows measurements, not opinions. It helps you decide, never processes your audio.\n\nLocal analysis. Transparent reasoning. £19 perpetual licence.",
    accent: "var(--brand-violet, #9277F2)",
  },
  {
    eyebrow: "Why Local-First",
    title: "Your work stays on your machine",
    body: "No cloud uploads. No subscription lock-in. No disappearing when a company shuts down.\n\nYou buy it, it works as long as your Mac does.\n\nEvery NITE DSP product follows this principle.",
    accent: "var(--brand-blue-bright)",
  },
  {
    eyebrow: "Get Started",
    title: "Three waitlists. First 50 spots each.",
    body: "Submit: nitedsp.co.uk/products/submit\nSLO: nitedsp.co.uk/products/smart-sample-manager\nKENN: nitedsp.co.uk/products/kenn\n\nOr try the free scorecard: nitedsp.co.uk/learn/guides/submission-scorecard\n\nQuestions? nitedsp@outlook.com",
    accent: "var(--state-success, #16a34a)",
  },
];

export default function DemoDeckPage() {
  const [current, setCurrent] = useState(0);
  const slide = SLIDES[current];

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--background)",
        color: "var(--foreground)",
      }}
    >
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem 1.5rem",
        }}
      >
        <div style={{ maxWidth: "48rem", width: "100%" }}>
          <span
            style={{
              fontFamily: "var(--font-geist-mono), monospace",
              fontSize: "0.7rem",
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: slide.accent,
            }}
          >
            {slide.eyebrow}
          </span>
          <h1
            style={{
              fontSize: "clamp(1.75rem, 5vw, 3rem)",
              fontWeight: 700,
              lineHeight: 1.15,
              letterSpacing: "-0.02em",
              marginTop: "1rem",
              color: "var(--foreground)",
            }}
          >
            {slide.title}
          </h1>
          <div
            style={{
              marginTop: "1.5rem",
              fontSize: "clamp(0.95rem, 1.5vw, 1.15rem)",
              lineHeight: 1.65,
              color: "var(--muted)",
              whiteSpace: "pre-line",
            }}
          >
            {slide.body}
          </div>
        </div>
      </div>

      <div
        style={{
          padding: "1rem 1.5rem 2rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          maxWidth: "48rem",
          width: "100%",
          margin: "0 auto",
        }}
      >
        <button
          type="button"
          onClick={() => setCurrent(Math.max(0, current - 1))}
          disabled={current === 0}
          style={{
            fontFamily: "var(--font-geist-mono), monospace",
            fontSize: "0.75rem",
            padding: "0.5rem 1rem",
            borderRadius: "6px",
            border: "1px solid var(--border)",
            background: "transparent",
            color: current === 0 ? "var(--muted-dim)" : "var(--foreground)",
            cursor: current === 0 ? "default" : "pointer",
          }}
        >
          Back
        </button>

        <div
          style={{
            display: "flex",
            gap: "0.35rem",
            alignItems: "center",
          }}
        >
          {SLIDES.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setCurrent(i)}
              style={{
                width: i === current ? "1.5rem" : "0.5rem",
                height: "0.35rem",
                borderRadius: "2px",
                border: "none",
                background:
                  i === current
                    ? "var(--brand-blue-bright)"
                    : "var(--border)",
                cursor: "pointer",
                transition: "width 0.2s",
              }}
              aria-label={`Slide ${i + 1}`}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={() =>
            setCurrent(Math.min(SLIDES.length - 1, current + 1))
          }
          disabled={current === SLIDES.length - 1}
          style={{
            fontFamily: "var(--font-geist-mono), monospace",
            fontSize: "0.75rem",
            padding: "0.5rem 1rem",
            borderRadius: "6px",
            border: "1px solid var(--border)",
            background: "transparent",
            color:
              current === SLIDES.length - 1
                ? "var(--muted-dim)"
                : "var(--foreground)",
            cursor:
              current === SLIDES.length - 1 ? "default" : "pointer",
          }}
        >
          Next
        </button>
      </div>

      <div
        style={{
          textAlign: "center",
          paddingBottom: "1rem",
          fontFamily: "var(--font-geist-mono), monospace",
          fontSize: "0.6rem",
          color: "var(--muted-dim)",
        }}
      >
        {current + 1} / {SLIDES.length} &middot; Use arrow keys or tap to
        navigate
      </div>
    </div>
  );
}
