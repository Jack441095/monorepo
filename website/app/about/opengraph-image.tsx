import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "About NITE DSP | Built by Jack Knowlton";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "ABOUT",
    title: "Built by someone who uses the tools",
    subtitle: "12 years in audio. Now building NITE DSP.",
    accent: OG_ACCENT.brand,
  });
}
