import type { Metadata } from "next";
import Link from "next/link";
import { pageMetadata } from "@/lib/seo";
import { ParaphraseBox } from "@/components/ParaphraseBox";
import { ParaphraseDonate } from "@/components/ParaphraseDonate";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = pageMetadata({
  title: "Paraphrase: Make AI text read natural",
  description:
    "A free writing aid that rewrites pasted text so it reads like a person wrote it. Four voices, pay what you like, no account needed.",
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
          <h1 className="section-title mt-4 text-foreground">Make AI text read like you wrote it.</h1>
          <p className="text-sm font-mono text-muted-dim mt-1">
            Essay &middot; Email &middot; Report &middot; Casual
          </p>
          <p className="body-large mt-6 font-sans">
            Paste the draft, pick a voice, and get a version that sounds natural instead of
            generated. Meaning and citations are preserved by design, free rewrites reset every
            day, and payments are pay-what-you-like, from nothing up.
          </p>
          <div className="mt-8 max-w-3xl">
            <ParaphraseBox />
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
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">Support the tool</span>
              <h2 className="section-title mt-4">Pay what you like.</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                Free rewrites reset every day. If you use it regularly, throwing something
                in keeps it running. Any amount, no account, one-time charge.
              </p>
            </div>
          </Reveal>
          <div className="mt-8">
            <ParaphraseDonate />
          </div>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container cta-panel depth-hover">
          <div>
            <span className="eyebrow">Privacy &amp; Pricing</span>
            <h2 className="section-title mt-4 text-foreground">Nothing stored. Pay what you like.</h2>
            <p className="mt-2 text-sm text-muted max-w-xl">
              Pasted text is streamed through and not stored. The soft paywall keeps the tool
              free for everyone; supporting it buys the hours that keep it running.
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