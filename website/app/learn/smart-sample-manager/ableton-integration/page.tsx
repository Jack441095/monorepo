import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Ableton Integration (Experimental)",
  description: "How Smart Sample Manager's experimental Ableton Live tag integration works.",
  alternates: { canonical: "/learn/smart-sample-manager/ableton-integration" },
};

export default function AbletonIntegrationPage() {
  return (
    <LearnLayout slug="ableton-integration" title="Ableton Integration (Experimental)">
      <div role="note" className="callout-warning">
        <strong>Experimental.</strong> This feature is still being validated against a range of
        real libraries. It is not an official Ableton partnership or integration.
      </div>

      <section>
        <LearnH2>What it does</LearnH2>
        <p className="mt-2">
          Smart Sample Manager can write your tags into the same metadata format Ableton Live&apos;s
          own sample browser reads, so your organisation shows up inside Ableton too --
          without maintaining a second, separate catalog.
        </p>
      </section>

      <section>
        <LearnH2>How to use it</LearnH2>
        <p className="mt-2">
          After tagging a sample (or a folder of samples), click{" "}
          <strong>WRITE TO ABLETON (EXPERIMENTAL)</strong>. Smart Sample Manager writes the tag
          metadata in the same sidecar location and format Ableton itself uses, so Live&apos;s
          browser picks it up the next time it reads that folder.
        </p>
      </section>

      <section>
        <LearnH2>Source-file safety</LearnH2>
        <p className="mt-2">
          This writes to a separate <code>Ableton Folder Info</code> sidecar folder placed
          alongside your samples -- the exact mechanism Ableton&apos;s own tagging uses. Your
          original audio files themselves are never modified, renamed, or moved.
        </p>
      </section>

      <section>
        <LearnH2>Limitations</LearnH2>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>This is specific to Ableton Live&apos;s sample browser -- other DAWs don&apos;t read this format.</li>
          <li>It has not been validated against every possible library structure or Ableton version yet.</li>
          <li>It is not an official Ableton feature, partnership, or integration.</li>
        </ul>
      </section>
    </LearnLayout>
  );
}
