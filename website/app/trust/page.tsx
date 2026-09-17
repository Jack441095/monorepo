import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "Trust & Privacy",
  description: "How NITE DSP software handles your files: local processing, data boundaries, and honest product limits.",
  path: "/trust",
});

const PILLARS = [
  {
    title: "Local by default",
    body: "NITE Submit reads and prepares documents entirely in memory on your Mac. SLO indexes and analyses audio on your machine. Our website demos run in your browser with illustrative data.",
  },
  {
    title: "What is not uploaded",
    body: "Your documents, your audio files, and your sample library are never uploaded by the apps. The beta request form composes an email in your own mail client, details stay on your machine until you send them.",
  },
  {
    title: "Honest boundaries",
    body: "Every product states what it does not do. Submit does not submit work for you and cannot guarantee department-specific rules. KENN explains mixes; it does not mix them for you. Thursday is infrastructure, not a chatbot.",
  },
];

const FAQ = [
  [
    "Does NITE Submit upload my files?",
    "No. Documents are processed locally on your Mac. Nothing is sent to a server as part of document review or naming.",
  ],
  [
    "Will Submit automatically submit my work?",
    "No. Submit helps you prepare, verify, and package a safely named copy. You always submit through your institution's own system, and a final manual check is recommended, Submit cannot know every department's specific rules.",
  ],
  [
    "How does verification work?",
    "Submit scans document structure and metadata locally, highlights verified entries, and flags uncertain fields for your approval before any copy is written. Your original file is never modified.",
  ],
  [
    "What happens when Submit is uncertain?",
    "Uncertain fields are flagged and explained rather than silently corrected. You decide what changes before a prepared copy is saved.",
  ],
  [
    "Is it a subscription?",
    "No. The first paid experiment is a planned £3 perpetual licence. The closed beta is free.",
  ],
];

export default function TrustPage() {
  return (
    <>
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Trust & Privacy</span>
          <h1 className="section-title mt-4 text-foreground">Your work stays yours.</h1>
          <p className="body-large mt-6">
            NITE DSP products are built so that the sensitive parts of creative work, documents,
            recordings, sample libraries, stay on your machine.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container">
          <div className="capability-grid spotlight-group">
            {PILLARS.map((p) => (
              <article key={p.title} className="capability">
                <h3 className="text-foreground">{p.title}</h3>
                <p>{p.body}</p>
              </article>
            ))}
          </div>
          <p className="mt-8 text-xs text-muted-dim max-w-2xl">
            For the formal position, read our{" "}
            <Link href="/privacy" className="text-link">privacy policy</Link>,{" "}
            <Link href="/terms" className="text-link">terms</Link>,{" "}
            <Link href="/eula" className="text-link">EULA</Link>, and{" "}
            <Link href="/refund-policy" className="text-link">refund policy</Link>.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container" style={{ maxWidth: "48rem" }}>
          <span className="eyebrow">FAQ</span>
          <h2 className="section-title mt-4 text-foreground">Common questions.</h2>
          <div className="mt-8 flex flex-col gap-3">
            {FAQ.map(([q, a]) => (
              <details key={q} className="surface-card p-5 rounded-lg border border-border/40">
                <summary className="cursor-pointer text-sm font-semibold text-foreground">{q}</summary>
                <p className="mt-3 text-xs leading-relaxed text-muted">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
