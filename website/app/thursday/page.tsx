import type { Metadata } from "next";
import Link from "next/link";
import { CtaButton } from "@/components/CtaButton";
import { Reveal } from "@/components/motion/Reveal";
import { StatusDot } from "@/components/motion/StatusDot";

export const metadata: Metadata = {
  title: "Thursday: The NITE DSP Intelligence Layer",
  description:
    "Thursday is the internal intelligence layer coordinating workflows and specialised agents across NITE DSP products. Infrastructure, not a chatbot.",
  alternates: { canonical: "/thursday" },
};

const PILLARS = [
  {
    title: "Orchestration",
    body: "Thursday routes work between NITE DSP tools, handing a prepared document to the right verifier, or analysis output to the right reviewer, without you gluing steps together.",
  },
  {
    title: "Workflows",
    body: "Repeatable multi-step pipelines are defined once and reused. A submission-preparation workflow or a library-rescan workflow runs the same way every time.",
  },
  {
    title: "Planning",
    body: "Complex jobs are broken into ordered steps before execution, so each specialised component knows exactly what it receives and what it owes next.",
  },
  {
    title: "Verification",
    body: "Outputs are checked before handoff. Work moving through Thursday carries its evidence with it, and failed checks stop the pipeline rather than passing problems downstream.",
  },
];

const NOTS = [
  ["Not a chatbot", "You don't converse with Thursday. It is infrastructure, it coordinates, it doesn't chat."],
  ["Not a cloud brain", "Thursday coordinates local tools. Your creative material stays on your machine."],
  ["Not a product (yet)", "Thursday is internal. It powers how NITE DSP products work together as the ecosystem grows."],
];

export default function ThursdayPage() {
  return (
    <>
      {/* Hero */}
      <section className="section product-hero relative overflow-hidden">
        <div className="site-container relative">
          <span className="eyebrow text-muted-dim">Internal Systems Family</span>
          <h1 className="section-title mt-4 text-foreground">The NITE DSP internal layer.</h1>
          <p className="text-sm font-mono text-muted-dim mt-1">
            Orchestration &middot; Planning &middot; Verification
          </p>
          <p className="body-large mt-6 font-sans">
            Every NITE DSP product does one job well. Thursday is the internal infrastructure layer that coordinates workflows between specialized components, plans multi-step jobs, and verifies results at every handoff. Thursday is internal infrastructure, not a public commercial product or consumer chatbot.
          </p>
          <div className="mt-8 flex flex-wrap gap-4 items-center">
            <span
              className="status-chip text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border inline-flex items-center gap-1"
              style={{ borderColor: "var(--border-strong)", color: "var(--muted)" }}
            >
              <StatusDot tone="muted" />
              Internal
            </span>
            <CtaButton state="NOTIFY_ME" label="Hear when this surfaces in products" secondary />
          </div>
        </div>
      </section>

      {/* Pillars */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">How It Works</span>
              <h2 className="section-title mt-4">Coordination with verification built in.</h2>
            </div>
          </Reveal>
          <div className="capability-grid spotlight-group mt-10">
            {PILLARS.map((p) => (
              <article key={p.title} className="capability">
                <h3 className="text-foreground">{p.title}</h3>
                <p>{p.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Anti-positioning */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">What Thursday Is Not</span>
            <h2 className="section-title mt-4">Infrastructure, not conversation.</h2>
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

      {/* Ecosystem context */}
      <section className="section section-rule">
        <div className="site-container cta-panel depth-hover">
          <div>
            <span className="eyebrow">The Ecosystem</span>
            <h2 className="section-title mt-4 text-foreground">One layer behind every tool.</h2>
            <p className="mt-2 text-sm text-muted max-w-xl">
              As Submit, SLO, and KENN mature, Thursday is what lets them hand work to each other, 
              safely, verifiably, locally.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 relative z-10">
            <Link href="/products" className="btn-secondary">
              See the products
            </Link>
            <Link href="/technology" className="btn-secondary">
              Read the technology
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
