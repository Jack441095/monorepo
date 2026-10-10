import type { Metadata } from "next";
import Link from "next/link";
import { pageMetadata } from "@/lib/seo";
import { ParaphraseBox } from "@/components/ParaphraseBox";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = pageMetadata({
  title: "Para-phase: Free writing aid",
  description:
    "A free writing aid that rewrites pasted text so it reads like a person wrote it. Four voices, free daily rewrites, no account needed.",
  path: "/paraphrase",
});

const HOW = [
  {
    title: "Keep every fact",
    body: "The rewrite engine is held to a meaning-preservation tripwire: citations, numbers, names and claims must survive. If overlap drops, you're told, not silently changed.",
  },
  {
    title: "Four voices",
    body: "Essay, email, report or casual. Each gets its own rewrite instructions. Formality and sentence rhythm differ, the meaning does not.",
  },
  {
    title: "Anonymous",
    body: "No account, no email. Free rewrites reset daily, and nothing you paste is stored after the session ends.",
  },
];

const NOTS = [
  ["Not a lab report generator", "It rewrites drafts. It does not research, fabricate data, or write your coursework for you."],
  ["Not a 'bypass' tool", "It is not sold as a way around detection. If your institution forbids certain software, that is your call. This is a drafting aid."],
  ["Not a magic button", "Good writing still needs your judgement. The tool flags when a rewrite may have drifted. You stay responsible for what you submit."],
];

export default function ParaphrasePage() {
  return (
    <>
      <section className="section product-hero relative overflow-hidden">
        <div className="site-container relative">
          <span className="eyebrow text-muted-dim">University Writing Aids</span>
          <h1 className="section-title mt-4 text-foreground">Para-phase</h1>
          <p className="text-sm font-mono text-muted-dim mt-1">
            Essay &middot; Email &middot; Report &middot; Casual
          </p>
          <p className="body-large mt-6 font-sans">
            Paste the draft, pick a voice, and get a version that sounds natural instead of
            generated. Meaning and citations are preserved by design, free rewrites reset every
            day. Para-phase is free to use.
          </p>
          <div className="mt-8 max-w-3xl">
            {/* The backend gate is separate from free pricing. Publish the form
                only after the production engine has passed a streaming check. */}
            {process.env.NEXT_PUBLIC_PARAPHRASE_ENABLED === "1" ? (
              <ParaphraseBox />
            ) : (
              <p className="surface-card rounded-lg border border-border/50 p-5 text-sm text-muted">
                Para-phase is free. Public rewriting is being prepared and is not available yet.
              </p>
            )}
          </div>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">How It Works</span>
              <h2 className="section-title mt-4">Rewrites with guardrails.</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                The engine verifies that your core words and structure survived the rewrite, and
                flags it when overlap drops rather than quietly rewriting history.
              </p>
            </div>
          </Reveal>
          <div className="capability-grid spotlight-group mt-10">
            {HOW.map((item) => (
              <article key={item.title} className="capability">
                <h3 className="text-foreground">{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">What It Is Not</span>
            <h2 className="section-title mt-4">A drafting aid, with a line.</h2>
          </Reveal>
          <div className="capability-grid spotlight-group mt-10">
            {NOTS.map(([title, body]) => (
              <article key={title} className="capability">
                <h3 className="text-foreground">{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container cta-panel depth-hover">
          <div>
            <span className="eyebrow">Privacy &amp; Pricing</span>
            <h2 className="section-title mt-4 text-foreground">Free daily rewrites. No account needed.</h2>
            <p className="mt-2 text-sm text-muted max-w-xl">
              Pasted text is streamed through and not stored. Daily limits help keep the
              free service available. You can try again when the limit resets.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 relative z-10">
            <Link href="/privacy" className="btn-secondary">
              Privacy policy
            </Link>
            <Link href="/support" className="btn-secondary">
              Get support
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
