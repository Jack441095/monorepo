import type { Metadata } from "next";
import { LearnLayout, LearnH2 } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Ableton Integration (Experimental)",
  description: "How SLO's experimental Ableton Live tag integration works.",
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
          SLO can write your tags into the same metadata format Ableton Live&apos;s
          own sample browser reads, so your organisation shows up inside Ableton too --
          without maintaining a second, separate catalog.
        </p>

        {/* Integration Diagram */}
        <div className="product-frame my-8 p-6 bg-surface-raised/40 border border-border/40 rounded-lg flex items-center justify-center">
          <svg width="640" height="240" viewBox="0 0 640 240" fill="none" xmlns="http://www.w3.org/2000/svg" className="max-w-full h-auto">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 2 L 8 5 L 0 8 z" fill="var(--muted-dim)" />
              </marker>
              <linearGradient id="glow-grad-v" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="var(--brand-blue)" />
                <stop offset="100%" stopColor="var(--brand-violet)" />
              </linearGradient>
            </defs>

            {/* Boundaries */}
            <rect x="10" y="10" width="280" height="220" rx="10" stroke="var(--border)" strokeWidth="0.8" strokeDasharray="3 3" fill="var(--surface-raised)" opacity="0.4" />
            <text x="25" y="32" fill="var(--muted-dim)" className="font-mono text-[9px] uppercase tracking-wider">SLO Local Sandbox</text>

            <rect x="350" y="10" width="280" height="220" rx="10" stroke="var(--border)" strokeWidth="0.8" strokeDasharray="3 3" fill="var(--surface-raised)" opacity="0.4" />
            <text x="365" y="32" fill="var(--muted-dim)" className="font-mono text-[9px] uppercase tracking-wider">Ableton Live Environment</text>

            {/* SLO DB */}
            <rect x="30" y="60" width="100" height="60" rx="6" fill="var(--surface)" stroke="var(--brand-blue)" strokeWidth="1.5" />
            <text x="80" y="88" textAnchor="middle" fill="var(--foreground)" className="font-sans text-xs font-semibold">SLO Index</text>
            <text x="80" y="102" textAnchor="middle" fill="var(--brand-blue-bright)" className="font-mono text-[9px] uppercase tracking-wider">SQLite DB</text>

            {/* Raw Audio Folder */}
            <rect x="170" y="130" width="110" height="70" rx="6" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
            <text x="225" y="160" textAnchor="middle" fill="var(--foreground)" className="font-sans text-xs font-semibold">User Samples</text>
            <text x="225" y="174" textAnchor="middle" fill="var(--muted)" className="font-mono text-[8px] uppercase tracking-wider">/Raw WAV Folder</text>

            {/* Ableton Folder Info */}
            <rect x="370" y="130" width="110" height="70" rx="6" fill="var(--surface)" stroke="var(--brand-violet)" strokeWidth="1.5" />
            <text x="425" y="155" textAnchor="middle" fill="var(--foreground)" className="font-sans text-xs font-semibold">Folder Info</text>
            <text x="425" y="167" textAnchor="middle" fill="var(--brand-violet)" className="font-mono text-[8px] uppercase tracking-wider">/xmp sidecars</text>
            <text x="425" y="180" textAnchor="middle" fill="var(--muted)" className="font-sans text-[8px] italic">Non-Destructive</text>

            {/* Ableton Live Browser */}
            <rect x="510" y="60" width="100" height="60" rx="6" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
            <text x="560" y="88" textAnchor="middle" fill="var(--foreground)" className="font-sans text-xs font-semibold">Live Browser</text>
            <text x="560" y="102" textAnchor="middle" fill="var(--muted-dim)" className="font-mono text-[9px] uppercase tracking-wider">DAW Host</text>

            {/* Connection Arrows */}
            <path d="M 130 90 L 170 135" stroke="var(--muted-dim)" strokeWidth="1" markerEnd="url(#arrow)" />
            <text x="135" y="118" fill="var(--muted-dim)" className="font-mono text-[8px] tracking-tight">READ-ONLY</text>

            <path d="M 130 80 L 370 145" stroke="var(--brand-violet)" strokeWidth="1.5" strokeDasharray="3 1" markerEnd="url(#arrow)" />
            <text x="210" y="88" fill="var(--brand-violet)" className="font-sans text-[9px] font-semibold bg-surface px-1">Write Tags</text>

            <path d="M 460 130 L 510 95" stroke="var(--muted-dim)" strokeWidth="1" markerEnd="url(#arrow)" />
            <text x="495" y="125" fill="var(--muted-dim)" className="font-mono text-[8px]">READ</text>

            <path d="M 280 165 L 370 165" stroke="var(--muted-dim)" strokeWidth="1" markerEnd="url(#arrow)" strokeDasharray="2 2" />
            <text x="325" y="160" textAnchor="middle" fill="var(--muted-dim)" className="font-mono text-[8px]">LINK</text>

            <path d="M 560 120 L 560 150 L 480 165" stroke="var(--muted-dim)" strokeWidth="1" markerEnd="url(#arrow)" />
          </svg>
        </div>
      </section>

      <section>
        <LearnH2>How to use it</LearnH2>
        <p className="mt-2">
          After tagging a sample (or a folder of samples), click{" "}
          <strong>WRITE TO ABLETON (EXPERIMENTAL)</strong>. SLO writes the tag
          metadata in the same sidecar location and format Ableton itself uses, so Live&apos;s
          browser picks it up the next time it reads that folder.
        </p>
      </section>

      <section>
        <LearnH2>Source-file safety</LearnH2>
        <p className="mt-2">
          This writes to a separate <code>Ableton Folder Info</code> sidecar folder placed
          alongside your samples — the exact mechanism Ableton&apos;s own tagging uses. Your
          original audio files are not modified, and since SLO operates in read-only mode during
          the private beta, your sample directory structure is not automatically rearranged.
        </p>
      </section>

      <section>
        <LearnH2>Limitations</LearnH2>
        <ul className="mt-2 list-disc pl-5 space-y-1">
          <li>This is specific to Ableton Live&apos;s sample browser — other DAWs don&apos;t read this format.</li>
          <li>It has not been validated against every possible library structure or Ableton version yet.</li>
          <li>It is not an official Ableton feature, partnership, or integration.</li>
        </ul>
      </section>
    </LearnLayout>
  );
}
