import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "SLO | Sample Library Optimiser by NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "NITE DSP",
    title: "SLO",
    subtitle: "Sample Library Optimiser",
    accent: OG_ACCENT.audio,
  });
}
