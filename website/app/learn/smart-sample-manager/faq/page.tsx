import type { Metadata } from "next";
import { LearnLayout } from "@/lib/learn";

export const metadata: Metadata = {
  title: "FAQ",
  description: "Frequently asked questions about SLO.",
  alternates: { canonical: "/learn/smart-sample-manager/faq" },
};

const FAQ = [
  {
    q: "What is SLO?",
    a: "An acoustic-similarity sample browser and organizer for VST3, AU, and Standalone hosts. It indexes your sample library locally, lets you audition and browse it, and helps you find sounds by how they actually sound.",
  },
  {
    q: "Does it upload my samples?",
    a: "No. Scanning, analysis, and matching all happen locally on your Mac. No sample audio is uploaded. Account authentication and licensing check-ins communicate with our platform services.",
  },
  {
    q: "Does it modify my samples?",
    a: "No — during the private beta, SLO operates in read-only classification mode and does not automatically move, rename, or delete your samples. The optional Ableton integration writes tags to a separate sidecar folder alongside your samples, not into the audio files themselves.",
  },
  {
    q: "What is Find Similar?",
    a: "Select a sample you already have, and it surfaces other samples in your library that sound like it, based on the audio itself.",
  },
  {
    q: "Can I search with a typed description, like \"dark punchy kick\"?",
    a: "Not currently. Find Similar compares real audio you select — it isn't a natural-language text search.",
  },
  {
    q: "Which DAWs are supported?",
    a: "SLO ships as VST3, AU, and a Standalone app, so it loads in any host that supports those formats. Ableton Live also gets an experimental tag-integration feature.",
  },
  {
    q: "Does it work offline?",
    a: "Yes. Once activated, it keeps working offline for a grace period before needing to re-check in, then quietly re-validates the next time you're online.",
  },
  {
    q: "How many computers can I activate?",
    a: "Each license currently supports a small number of simultaneous activations. Check your account page for your exact entitlement, and deactivate an old machine there before activating a new one if you're at the limit.",
  },
  {
    q: "Can I use samples on an external drive?",
    a: "Yes — point SLO at any folder your Mac can see. If the drive is disconnected later, rescan once it's reconnected to pick up any changes.",
  },
  {
    q: "What happens if I reinstall macOS or get a new Mac?",
    a: "Deactivate the license on the old machine from your account page (or contact support if that's not possible), then activate on the new one.",
  },
  {
    q: "What happens to my library when I reopen the app?",
    a: "SLO doesn't automatically reload your last library on launch — you'll need to rescan the same folder. Thanks to caching, this is fast, since already-analysed files are skipped.",
  },
  {
    q: "How do updates work?",
    a: "Download the current release from your account page and reinstall over the existing app. Your license, sample library, and cache all carry over.",
  },
  {
    q: "Is the Ableton integration an official Ableton feature?",
    a: "No — it's an experimental NITE DSP feature that writes to the same metadata format Ableton's own browser reads. It isn't an official Ableton partnership or integration.",
  },
  {
    q: "Is Windows supported?",
    a: "Not yet. SLO is macOS-only for now. Windows is on the roadmap, not currently available.",
  },
];

export default function FaqPage() {
  return (
    <LearnLayout slug="faq" title="FAQ">
      <dl className="space-y-6">
        {FAQ.map((item) => (
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
