import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "Why Local-First Matters for Creative Tools",
  description: "Cloud dependencies create latency, privacy risks, and subscription lock-in. Local-first tools give creative professionals control over their work.",
  path: "/learn/insights/local-first-creative-tools",
});

export default function LocalFirstPage() {
  return (
    <article className="section">
      <div className="site-container" style={{ maxWidth: "42rem" }}>
        <Link href="/learn" className="text-link text-xs">&larr; Back to Learn</Link>
        <span className="eyebrow mt-6 block text-brand-blue-bright">Insight</span>
        <h1 className="mt-4 text-3xl sm:text-4xl font-bold tracking-tight text-foreground leading-tight">
          Why local-first matters for creative tools
        </h1>
        <p className="mt-4 text-sm text-muted">
          The case for keeping your creative work on your machine.
        </p>

        <div className="mt-10 prose-custom">
          <p>
            The default model for modern software is cloud-first. Your data lives on someone else&apos;s servers, processed by their infrastructure, gated by their subscription. For many tools, that tradeoff makes sense. For creative work, it often doesn&apos;t.
          </p>

          <h2>Your samples are your intellectual property</h2>
          <p>
            Producers invest thousands of hours and pounds building sample libraries. These collections represent a unique creative voice. Your sound. Uploading them to a cloud service for analysis means trusting a third party with your competitive advantage.
          </p>
          <p>
            Local-first means your audio never leaves your machine. There&apos;s no upload step, no server processing, no data retention policy to read. The analysis happens in memory on your Mac and the results stay on your local drive.
          </p>

          <h2>Latency kills flow</h2>
          <p>
            Creative work depends on staying in flow state. Every round trip to a server, even a fast one, introduces latency that breaks concentration. When you&apos;re searching for the right sound in the middle of a session, you need results in milliseconds, not seconds.
          </p>
          <p>
            Local computation on Apple Silicon is fast enough to deliver real-time acoustic search across tens of thousands of samples. No internet connection required. Works on a plane, in a studio with unreliable WiFi, or anywhere you make music.
          </p>

          <h2>No subscription, no lock-in</h2>
          <p>
            Cloud services create dependency. If the company changes pricing, shuts down, or modifies terms of service, your workflow breaks. Local-first tools are resilient by design. They work as long as your computer does.
          </p>
          <p>
            That doesn&apos;t mean local-first tools can&apos;t evolve. Updates, new features, and improvements ship as software updates. But the core functionality (your data, your analysis, your results) belongs to you unconditionally.
          </p>

          <h2>The NITE DSP approach</h2>
          <p>
            Every NITE DSP tool follows the same principle: process locally, store locally, never upload. Whether it&apos;s Submit checking document structure or SLO indexing acoustic features, the work happens on your machine. We build the intelligence. You keep the data.
          </p>

          <div className="mt-10 flex gap-4">
            <Link href="/products" className="btn-primary">
              Explore the tools
            </Link>
            <Link href="/learn/insights/why-filenames-fail" className="btn-secondary">
              Why filenames fail
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}
