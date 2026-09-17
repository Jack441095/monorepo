import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "How Acoustic Timbre Search Works",
  description: "A non-technical explanation of how SLO finds similar sounds by analysing the audio signal itself, not filenames or tags.",
  path: "/learn/insights/acoustic-timbre-search",
});

export default function AcousticTimbreSearchPage() {
  return (
    <article className="section">
      <div className="site-container" style={{ maxWidth: "42rem" }}>
        <Link href="/learn" className="text-link text-xs">&larr; Back to Learn</Link>
        <span className="eyebrow mt-6 block text-brand-blue-bright">Insight</span>
        <h1 className="mt-4 text-3xl sm:text-4xl font-bold tracking-tight text-foreground leading-tight">
          How acoustic timbre search works
        </h1>
        <p className="mt-4 text-sm text-muted">
          A plain-language explanation of the signal analysis behind SLO.
        </p>

        <div className="mt-10 prose-custom">
          <p>
            When you hear a sound, your brain processes it in a fraction of a second. Bright or dark. Sharp or soft. Sustained or percussive. These aren&apos;t just subjective impressions. They correspond to measurable physical properties of the audio signal.
          </p>

          <h2>What we measure</h2>
          <p>
            SLO extracts a set of acoustic features from every sample in your library. Each one captures a different dimension of what the sound actually <em>is</em>:
          </p>
          <ul>
            <li><strong>Spectral centroid</strong> is the &ldquo;centre of gravity&rdquo; of the frequency spectrum. High values mean bright, low values mean dark.</li>
            <li><strong>Transient envelope</strong> describes how quickly the sound attacks and decays. A snare has a fast rise. A pad has a slow one.</li>
            <li><strong>Harmonic structure</strong> tells you whether the sound is tonal (like a bass note) or noisy (like a hi-hat).</li>
            <li><strong>Spectral flux</strong> measures how much the frequency content changes over time. Static sounds score low, evolving textures score high.</li>
          </ul>
          <p>
            Together, these features form a high-dimensional &ldquo;fingerprint&rdquo; for each sample. Two sounds with similar fingerprints will sound similar to your ear, no matter what their filenames say.
          </p>

          <h2>Similarity as distance</h2>
          <p>
            Once every sample has a fingerprint, finding similar sounds becomes a distance calculation. &ldquo;Find me something like this kick&rdquo; really just means: find the samples whose fingerprints are closest to this one in the feature space.
          </p>
          <p>
            That&apos;s why SLO can surface a forgotten sample buried six folders deep in a pack you bought three years ago. The filename might be <code>AB_Layer_03_v2_final.wav</code>, but its acoustic fingerprint sits right next to the reference kick you dragged in.
          </p>

          <h2>All local, all the time</h2>
          <p>
            Every calculation runs on your machine. The feature extraction, the indexing, the similarity search. Nothing leaves your computer. Your samples are your intellectual property, and SLO treats them that way.
          </p>
          <p>
            The initial scan of a large library takes a few minutes. After that, results come back in milliseconds. The index is cached locally, so rescans are nearly instant.
          </p>

          <div className="mt-10 flex gap-4">
            <Link href="/products/smart-sample-manager#join-waitlist" className="btn-primary">
              Join the SLO waitlist
            </Link>
            <Link href="/learn/insights/local-first-creative-tools" className="btn-secondary">
              Why local-first matters
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}
