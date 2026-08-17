import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Visual Map",
  description: "Browse your sample library laid out by sonic similarity.",
  alternates: { canonical: "/learn/smart-sample-manager/visual-map" },
};

export default function VisualMapPage() {
  return (
    <LearnLayout slug="visual-map" title="Visual Map">
      <section>
        <LearnH2>What it is</LearnH2>
        <p className="mt-2">
          As Smart Sample Manager indexes your library, every sample is plotted as a point on a
          2D map. Points that end up near each other tend to sound alike. It&apos;s a different
          way to browse than scrolling a folder tree — explore by ear, moving through clusters
          of related sounds.
        </p>
      </section>

      <section>
        <LearnH2>Using it</LearnH2>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>Click a point to select that sample — its details appear in the metadata panel.</li>
          <li>
            Use <strong>PLAY</strong> / <strong>STOP</strong> to audition it.
          </li>
          <li>
            Use <strong>FIND SIMILAR</strong> on a selected point to list other closely-related
            samples — see{" "}
            <a href="/learn/smart-sample-manager/find-similar" className="underline">
              Find Similar
            </a>
            .
          </li>
        </ul>
      </section>

      <section>
        <LearnH2>Interpreting the layout</LearnH2>
        <p className="mt-2">
          Proximity on the map reflects sonic similarity as analysed by Smart Sample Manager --
          treat it as a exploration tool for discovering related sounds, not as a precise
          scientific measurement of any single audio characteristic. With a very small library
          (a handful of samples), the map uses a simple layout rather than a full similarity
          projection, since there isn&apos;t enough data yet for a meaningful one.
        </p>
      </section>

      <section>
        <LearnH2>When it updates</LearnH2>
        <p className="mt-2">
          The map fills in live as your library scans. Adding more samples later and rescanning
          extends it with the newly analysed sounds.
        </p>
      </section>
    </LearnLayout>
  );
}
