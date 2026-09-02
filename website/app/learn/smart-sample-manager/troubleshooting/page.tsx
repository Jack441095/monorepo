import type { Metadata } from "next";
import { LearnLayout } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Troubleshooting",
  description: "Fixes for common SLO problems.",
  alternates: { canonical: "/learn/smart-sample-manager/troubleshooting" },
};

const ITEMS = [
  {
    q: "SLO doesn't appear in my DAW",
    a: "Rescan your plugin folders in your DAW's preferences/settings (most DAWs do this automatically on the next launch, but not all). Confirm you're looking for the format you installed, VST3 or Audio Unit, and that your DAW supports it.",
  },
  {
    q: "My DAW's plugin scan has an issue",
    a: "Some DAWs cache a failed scan and won't retry automatically. Look for a \"rescan\"/\"reset plugin list\" option specifically, rather than just reopening the DAW.",
  },
  {
    q: "Activation failed",
    a: "Double-check you're using the exact license key shown on your account page, and that you have an internet connection for the first activation (offline use is supported after that, see the FAQ). If you've reached your device limit, deactivate an old machine from your account page first.",
  },
  {
    q: "My library won't index / a scan seems stuck",
    a: "Large libraries take longer on the first pass, check whether the sample count in the top-right is still increasing before assuming it's frozen. If it's genuinely stopped changing for several minutes on a small library, quit and relaunch, then rescan the same folder (already-analysed files are skipped, so this is fast).",
  },
  {
    q: "A sample won't preview",
    a: "Confirm the sample is selected (its details should show in the metadata panel) before clicking PLAY. If the underlying file has been moved, renamed, or deleted since your last scan, rescan the folder to refresh the library.",
  },
  {
    q: "\"Find Similar\" isn't available",
    a: "This needs a sample selected first, and your library to have finished its initial scan. If you just added samples, give the scan a moment to complete.",
  },
  {
    q: "The visual map looks sparse or empty",
    a: "With only a handful of samples indexed, the map uses a simple placeholder layout rather than a full similarity projection, this is expected for very small libraries, not a bug.",
  },
  {
    q: "A drive with my samples is disconnected/offline",
    a: "SLO only reads files that exist at scan time. If a drive is disconnected, those samples won't be reachable until it's reconnected, reconnect it and rescan.",
  },
  {
    q: "Problem downloading the installer",
    a: "Downloads are tied to your account entitlement, make sure you're signed in on the account page and try the download link again. If it still fails, contact support with your account email.",
  },
  {
    q: "Offline license question",
    a: "Once activated, SLO keeps working offline for a grace period before it needs to re-check in, see the FAQ for the exact window. If you're past that window and can't get online, contact support.",
  },
  {
    q: "Update problem",
    a: "Download the current release from your account page and reinstall over the existing app, your license, sample library, and cache are untouched by an update.",
  },
];

export default function TroubleshootingPage() {
  return (
    <LearnLayout slug="troubleshooting" title="Troubleshooting">
      <dl className="space-y-6">
        {ITEMS.map((item) => (
          <div key={item.q}>
            <dt className="font-medium" style={{ color: "var(--foreground)" }}>
              {item.q}
            </dt>
            <dd className="mt-2">{item.a}</dd>
          </div>
        ))}
      </dl>
    </LearnLayout>
  );
}
