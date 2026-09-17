import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "Why Filenames Fail: The Hidden Cost of Naming Conventions",
  description: "Filename conventions were designed for human memory, not acoustic retrieval. Here's why they break down at scale, and what replaces them.",
  path: "/learn/insights/why-filenames-fail",
});

export default function WhyFilenamesFailPage() {
  return (
    <article className="section">
      <div className="site-container" style={{ maxWidth: "42rem" }}>
        <Link href="/learn" className="text-link text-xs">&larr; Back to Learn</Link>
        <span className="eyebrow mt-6 block text-brand-blue-bright">Insight</span>
        <h1 className="mt-4 text-3xl sm:text-4xl font-bold tracking-tight text-foreground leading-tight">
          Why filenames fail at scale
        </h1>
        <p className="mt-4 text-sm text-muted">
          The hidden cost of naming conventions in creative sample libraries.
        </p>

        <div className="mt-10 prose-custom">
          <p>
            Every producer starts the same way. A folder called <code>Kicks</code>, another called <code>Snares</code>, maybe a <code>_Favourites</code> directory. It works when you have 500 samples. It collapses at 5,000. By 50,000, you&apos;re spending more time searching than producing.
          </p>

          <h2>The naming problem is structural</h2>
          <p>
            Filenames encode what the creator thought about a sound at the moment of export. <code>XK29_0047_hard.wav</code> tells you nothing about spectral content, transient shape, or timbral similarity. A sample pack author&apos;s mental model rarely matches yours.
          </p>
          <p>
            Folder hierarchies impose a single taxonomy. But sounds don&apos;t belong to one category. A tuned 808 is both a kick and a bass. A foley hit might work as a snare or a transition effect. Rigid trees force a choice that limits discovery.
          </p>

          <h2>Scale makes it worse</h2>
          <p>
            At 10,000 samples, duplicates creep in under different names. At 50,000, entire folders become black boxes. You know something good is in there, but the cost of auditioning files one by one exceeds the value of finding it.
          </p>
          <p>
            The result is predictable: producers default to the same 200 sounds they already know. The other 49,800 files sit unused, representing wasted money and missed creative opportunity.
          </p>

          <h2>The alternative: search by sound</h2>
          <p>
            Imagine you could describe what you want acoustically (&ldquo;something with a sharp transient and warm low-mid body&rdquo;) and get ranked results from your entire library in under a second. The naming problem disappears. You don&apos;t need to rename anything. You don&apos;t need to reorganise folders. The signal itself becomes the index.
          </p>
          <p>
            This is what acoustic timbre search does. Instead of relying on metadata that was wrong or incomplete from day one, it analyses the waveform directly: spectral centroid, transient envelope, harmonic content, and dozens of other measurable features.
          </p>

          <h2>What this means for your workflow</h2>
          <p>
            Stop organising. Start finding. The time you spend renaming and sorting files is time you could spend making music. Let the audio tell you what it is.
          </p>

          <div className="mt-10 flex gap-4">
            <Link href="/products/smart-sample-manager" className="btn-primary">
              See how SLO works
            </Link>
            <Link href="/learn/insights/acoustic-timbre-search" className="btn-secondary">
              How timbre search works
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}
