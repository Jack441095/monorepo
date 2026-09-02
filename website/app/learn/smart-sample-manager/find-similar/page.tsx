import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Find Similar",
  description: "How Find Similar works in SLO, acoustic similarity, not text search.",
  alternates: { canonical: "/learn/smart-sample-manager/find-similar" },
};

export default function FindSimilarPage() {
  return (
    <LearnLayout slug="find-similar" title="Find Similar">
      <section>
        <LearnH2>What it does</LearnH2>
        <p className="mt-2">
          Select a sample you already have, and Find Similar surfaces other samples in your
          library that sound like it, based on the actual audio content, not the filename or
          folder it&apos;s in.
        </p>
      </section>

      <section>
        <LearnH2>What &quot;similar&quot; means here</LearnH2>
        <p className="mt-2">
          This is <strong>audio-to-audio acoustic similarity</strong>, not a text search. You
          can&apos;t type a description like &quot;dark punchy kick&quot; and get results --
          you select a real sample you already have, and the comparison happens against your
          library&apos;s actual sound.
        </p>
      </section>

      <section>
        <LearnH2>How to use it</LearnH2>
        <ol className="mt-2 list-decimal pl-5 space-y-1">
          <li>Select a sample, either from the browser grid or a point on the visual map.</li>
          <li>
            Click <strong>FIND SIMILAR</strong>.
          </li>
          <li>
            A list of up to 15 similar samples appears, each with its name and instrument type.
          </li>
        </ol>
        <p className="mt-3">
          If nothing is selected yet, SLO will ask you to select a sample
          first. If your library is still being indexed, or it&apos;s the only sample in the
          library, you may see a message that no similar samples were found yet, give the
          initial scan time to finish and try again.
        </p>
      </section>

      <section>
        <LearnH2>What it doesn&apos;t do</LearnH2>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>It doesn&apos;t accept a typed description or natural-language query.</li>
          <li>It doesn&apos;t search outside your indexed library.</li>
          <li>It doesn&apos;t modify, move, or rename any of your files.</li>
        </ul>
      </section>
    </LearnLayout>
  );
}
