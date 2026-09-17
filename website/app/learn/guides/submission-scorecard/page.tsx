"use client";

import { useState } from "react";
import Link from "next/link";

const QUESTIONS = [
  {
    id: "filename",
    question: "Does your filename match the department's required format?",
    options: [
      { label: "Yes, I've checked the brief", score: 3 },
      { label: "I think so, but I haven't double-checked", score: 1 },
      { label: "I'm not sure what the format should be", score: 0 },
    ],
  },
  {
    id: "format",
    question: "Is your file in the correct format (e.g. PDF) and under the size limit?",
    options: [
      { label: "Yes, exported as the required format and checked the size", score: 3 },
      { label: "It's a PDF but I haven't checked the size limit", score: 1 },
      { label: "I'm submitting a .docx / I haven't checked", score: 0 },
    ],
  },
  {
    id: "metadata",
    question: "Have you checked the PDF metadata (author, title fields)?",
    options: [
      { label: "Yes, I've reviewed and cleared any personal info", score: 3 },
      { label: "I didn't know PDFs had metadata", score: 0 },
      { label: "I've heard of this but haven't checked", score: 1 },
    ],
  },
  {
    id: "formatting",
    question: "Does your document meet the formatting requirements (font, spacing, margins)?",
    options: [
      { label: "Yes, I've matched every spec in the brief", score: 3 },
      { label: "I used a template, should be fine", score: 2 },
      { label: "I haven't checked the formatting requirements", score: 0 },
    ],
  },
  {
    id: "references",
    question: "Is every in-text citation matched with a reference list entry?",
    options: [
      { label: "Yes, I've cross-checked every one", score: 3 },
      { label: "Most of them, I think", score: 1 },
      { label: "I haven't checked / no references needed", score: 2 },
    ],
  },
  {
    id: "plagiarism",
    question: "Have you run a similarity check before the official one?",
    options: [
      { label: "Yes, I used the draft submission option", score: 3 },
      { label: "No, but I've paraphrased everything properly", score: 1 },
      { label: "I didn't know I could check before submitting", score: 0 },
    ],
  },
  {
    id: "supporting",
    question: "Are all appendices and supporting files included and labelled?",
    options: [
      { label: "Yes, everything is packaged and named clearly", score: 3 },
      { label: "I have supporting files but haven't organised them", score: 1 },
      { label: "No supporting files needed", score: 3 },
    ],
  },
  {
    id: "proofread",
    question: "Have you done a final read-through specifically looking for errors?",
    options: [
      { label: "Yes, I read it in a different format (printed/different font)", score: 3 },
      { label: "I skimmed it quickly", score: 1 },
      { label: "No, I'll just submit it", score: 0 },
    ],
  },
];

function getResult(score: number, max: number) {
  const pct = (score / max) * 100;
  if (pct >= 90) return {
    grade: "Ready to submit",
    color: "var(--state-success, #16a34a)",
    message: "Your submission looks well-prepared. You've checked the things that most students miss. Go submit with confidence.",
  };
  if (pct >= 60) return {
    grade: "Almost there",
    color: "var(--state-warning, #d97706)",
    message: "You're in decent shape but there are a few areas that could trip you up. Review the items you scored low on before submitting.",
  };
  return {
    grade: "Needs attention",
    color: "var(--state-error, #dc2626)",
    message: "There are several areas that could cost you marks or cause a rejection. Take 10 minutes to work through the checklist before you submit.",
  };
}

export default function SubmissionScorecardPage() {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);

  const totalAnswered = Object.keys(answers).length;
  const allAnswered = totalAnswered === QUESTIONS.length;
  const score = Object.values(answers).reduce((a, b) => a + b, 0);
  const maxScore = QUESTIONS.length * 3;
  const result = getResult(score, maxScore);
  const pct = Math.round((score / maxScore) * 100);

  return (
    <>
      <section className="section product-hero relative overflow-hidden">
        <div className="site-container relative" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow text-brand-blue-bright">Free Tool</span>
          <h1 className="section-title mt-4 text-foreground">
            Is your submission ready?
          </h1>
          <p className="body-large mt-6">
            Answer 8 quick questions and find out if your coursework is ready to submit,
            or if there are things you should check first.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container" style={{ maxWidth: "42rem" }}>
          {!submitted ? (
            <div className="flex flex-col gap-6">
              {QUESTIONS.map((q, i) => (
                <div
                  key={q.id}
                  className="surface-card p-6 rounded-lg border border-border/40"
                >
                  <div className="flex items-baseline gap-3 mb-4">
                    <span
                      className="font-mono text-sm font-bold"
                      style={{ color: "var(--brand-blue-bright)" }}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <p className="text-sm font-semibold text-foreground">
                      {q.question}
                    </p>
                  </div>
                  <div className="flex flex-col gap-2">
                    {q.options.map((opt) => (
                      <button
                        key={opt.label}
                        type="button"
                        onClick={() =>
                          setAnswers((prev) => ({ ...prev, [q.id]: opt.score }))
                        }
                        className="text-left px-4 py-3 rounded-md border text-sm transition-colors"
                        style={{
                          borderColor:
                            answers[q.id] === opt.score
                              ? "var(--brand-blue-bright)"
                              : "var(--border)",
                          background:
                            answers[q.id] === opt.score
                              ? "rgba(86,168,255,0.08)"
                              : "transparent",
                          color:
                            answers[q.id] === opt.score
                              ? "var(--foreground)"
                              : "var(--muted)",
                        }}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}

              <div className="mt-4 flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => setSubmitted(true)}
                  disabled={!allAnswered}
                  className="btn-primary"
                  style={{ opacity: allAnswered ? 1 : 0.4 }}
                >
                  See my score
                </button>
                {!allAnswered && (
                  <span className="text-xs text-muted-dim">
                    {totalAnswered} of {QUESTIONS.length} answered
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              <div
                className="surface-card p-8 rounded-lg border text-center"
                style={{ borderColor: result.color }}
              >
                <p
                  className="font-mono text-sm font-bold uppercase tracking-wider"
                  style={{ color: result.color }}
                >
                  {result.grade}
                </p>
                <p
                  className="mt-4 font-mono text-4xl font-bold"
                  style={{ color: "var(--foreground)" }}
                >
                  {score}/{maxScore}
                </p>
                <div
                  className="mt-4 mx-auto h-2 rounded-full overflow-hidden"
                  style={{
                    background: "var(--border)",
                    maxWidth: "16rem",
                  }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${pct}%`,
                      background: result.color,
                    }}
                  />
                </div>
                <p className="mt-6 text-sm text-muted leading-relaxed max-w-md mx-auto">
                  {result.message}
                </p>
              </div>

              <div className="surface-card p-6 rounded-lg border border-border/40">
                <h2 className="text-base font-semibold text-foreground mb-2">
                  Your answers
                </h2>
                <div className="flex flex-col gap-3">
                  {QUESTIONS.map((q) => {
                    const s = answers[q.id] ?? 0;
                    const color =
                      s >= 3
                        ? "var(--state-success, #16a34a)"
                        : s >= 2
                        ? "var(--state-warning, #d97706)"
                        : "var(--state-error, #dc2626)";
                    return (
                      <div
                        key={q.id}
                        className="flex items-start gap-3 text-sm"
                      >
                        <span
                          className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
                          style={{ background: color }}
                        />
                        <span className="text-muted">{q.question}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="surface-card p-6 rounded-lg border border-border/40">
                <h2 className="text-base font-semibold text-foreground mb-2">
                  Want this checked automatically?
                </h2>
                <p className="text-sm text-muted leading-relaxed">
                  Submit checks filenames, metadata, formatting, and anonymisation
                  automatically. It runs on your Mac, never touches your content,
                  and gives you a verification receipt.
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Link href="/products/submit#join-waitlist" className="btn-primary">
                    Join the Submit waitlist
                  </Link>
                  <Link href="/learn/guides/submission-checklist" className="btn-secondary">
                    Read the full checklist
                  </Link>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  setAnswers({});
                  setSubmitted(false);
                }}
                className="text-link text-sm self-start"
              >
                Take it again
              </button>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
