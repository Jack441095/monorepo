import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Installation",
  description: "How to install SLO as VST3, Audio Unit, or Standalone on macOS.",
  alternates: { canonical: "/learn/smart-sample-manager/installation" },
};

export default function InstallationPage() {
  return (
    <LearnLayout slug="installation" title="Installation">
      <p>
        SLO currently runs on macOS as a VST3 plugin, an Audio Unit, and a
        Standalone application. Windows support is planned but not yet available.
      </p>

      <section>
        <LearnH2>Where each format lives</LearnH2>
        <p className="mt-2">The installer places each format in its standard macOS location:</p>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>
            <strong>VST3</strong> &mdash; <code>~/Library/Audio/Plug-Ins/VST3/</code>
          </li>
          <li>
            <strong>Audio Unit</strong> &mdash; <code>~/Library/Audio/Plug-Ins/Components/</code>
          </li>
          <li>
            <strong>Standalone</strong> &mdash; <code>/Applications/</code>
          </li>
        </ul>
        <p className="mt-2">
          You don&apos;t need to move anything manually, and nothing else needs to be installed
          separately, every dependency SLO needs is bundled inside the app
          itself.
        </p>
      </section>

      <section>
        <LearnH2>First launch</LearnH2>
        <p className="mt-2">
          If macOS shows a Gatekeeper prompt on first launch, that&apos;s the normal first-run
          check for any downloaded application, follow the on-screen option to open it. You
          won&apos;t be asked to install Homebrew, a package manager, or any other developer
          tooling to run SLO; if anything ever asks you to, that&apos;s not
          expected behaviour and worth reporting to support.
        </p>
      </section>

      <section>
        <LearnH2>Loading the plugin in your DAW</LearnH2>
        <p className="mt-2">
          After installing, rescan plugins in your DAW if it doesn&apos;t pick up the new VST3/AU
          automatically (most DAWs do this on the next launch). SLO will appear
          as <strong>SLO</strong> under NITE DSP in your plugin browser.
        </p>
      </section>

      <section>
        <LearnH2>Uninstalling</LearnH2>
        <p className="mt-2">
          Remove the app from <code>/Applications</code>, and the plugin files from the two
          Plug-Ins folders above. Your sample library itself is untouched, SLO
          only reads your audio files; during the private beta, it does not
          automatically move, rename, or delete your samples.
        </p>
      </section>

      <p className="text-sm" style={{ color: "var(--muted-dim)" }}>
        Next: <a href="/learn/smart-sample-manager/getting-started" className="underline">
          Getting Started
        </a>{" "}
        walks through activation and your first library scan.
      </p>
    </LearnLayout>
  );
}
