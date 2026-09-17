import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "Services | NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "FREELANCE & CONTRACT",
    title: "Audio engineering, DSP, and product work for hire.",
    subtitle: "nitedsp.co.uk/services",
    accent: OG_ACCENT.brand,
  });
}
