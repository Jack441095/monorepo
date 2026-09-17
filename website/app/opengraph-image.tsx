import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

// Site-wide default card. This is what every page without its own
// opengraph-image inherits, so it carries brand-level messaging — it used to
// be an SLO product card, which meant sharing the homepage, a legal page or
// any non-SLO product advertised SLO.
export const alt = "NITE DSP | intelligent tools for creative workflows";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "NITE DSP",
    title: "Intelligent tools for creative workflows",
    subtitle: "Local-first macOS software",
    accent: OG_ACCENT.brand,
  });
}
