import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Getting Started",
  description: "Install SLO, activate it, and index your first sample library.",
  alternates: { canonical: "/learn/smart-sample-manager/getting-started" },
};

export default function GettingStartedPage() {
  return (
    <LearnLayout slug="getting-started" title="Getting Started">
      <p>
        This walks through everything from opening SLO for the first time to
        finding a similar-sounding sample and dragging it into your DAW. It should take a few
        minutes.
      </p>

      <section>
        <LearnH2>1. Open SLO</LearnH2>
        <p className="mt-2">
          Launch it as a Standalone application, or load it as a VST3 or Audio Unit plugin in
          your DAW. All three run the same interface. For plugin-specific install locations, see{" "}
          <a href="/learn/smart-sample-manager/installation" className="underline">
            Installation
          </a>
          .
        </p>
      </section>

      <section>
        <LearnH2>2. Sign in and activate</LearnH2>
        <p className="mt-2">
          Sign in to your NITE DSP account from{" "}
          <a href="/account" className="underline">
            nitedsp.co.uk/account
          </a>{" "}
          to see your entitlement and license key. Activation inside the app itself uses that
          license key and works offline after the first successful check — you don&apos;t need
          to be online every time you open the app.
        </p>
      </section>

      <section>
        <LearnH2>3. Add your first sample library</LearnH2>
        <p className="mt-2">
          Click <strong>SCAN FOLDER</strong> and choose the folder containing your samples.
          SLO analyses every audio file it finds, entirely on your machine --
          nothing is uploaded. You&apos;ll see the sample count in the top-right corner climb as
          it works, and points begin appearing on the visual map as each sample is processed.
        </p>
        <p className="mt-3">
          A large library can take a while the first time, since every file needs analysing.
          Rescanning the same folder later is much faster, because already-analysed files are
          skipped.
        </p>
      </section>

      <section>
        <LearnH2>4. Preview a sound</LearnH2>
        <p className="mt-2">
          Select a sample — either from the grid or a point on the visual map — and use{" "}
          <strong>PLAY</strong> / <strong>STOP</strong> to audition it before committing to
          anything.
        </p>
      </section>

      <section>
        <LearnH2>5. Find a similar sound</LearnH2>
        <p className="mt-2">
          With a sample selected, click <strong>FIND SIMILAR</strong>. SLO
          compares the actual audio — not the filename — and lists other samples in your
          library that sound like it. See{" "}
          <a href="/learn/smart-sample-manager/find-similar" className="underline">
            Find Similar
          </a>{" "}
          for more detail.
        </p>
      </section>

      <section>
        <LearnH2>6. Explore the visual map</LearnH2>
        <p className="mt-2">
          Every indexed sample is plotted as a point. Sounds near each other tend to sound
          alike, so the map is a way to browse by ear instead of by folder. See{" "}
          <a href="/learn/smart-sample-manager/visual-map" className="underline">
            Visual Map
          </a>
          .
        </p>
      </section>

      <section>
        <LearnH2>7. Use the sound</LearnH2>
        <p className="mt-2">
          Drag the sample straight into your DAW&apos;s timeline or sampler from wherever it
          appears in SLO.
        </p>
      </section>

      <section>
        <LearnH2>One thing to know: reopening your library</LearnH2>
        <p className="mt-2">
          SLO doesn&apos;t automatically reload your last library when you
          reopen the app — you&apos;ll need to click <strong>SCAN FOLDER</strong> and choose the
          same folder again. Thanks to caching, this is quick (already-analysed files aren&apos;t
          re-processed), but it isn&apos;t automatic today.
        </p>
      </section>

      <section>
        <LearnH2>Where to go next</LearnH2>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>
            <a href="/learn/smart-sample-manager/ableton-integration" className="underline">
              Ableton integration (experimental)
            </a>
          </li>
          <li>
            <a href="/learn/smart-sample-manager/troubleshooting" className="underline">
              Troubleshooting
            </a>
          </li>
          <li>
            <a href="/learn/smart-sample-manager/faq" className="underline">
              FAQ
            </a>
          </li>
        </ul>
      </section>
    </LearnLayout>
  );
}
