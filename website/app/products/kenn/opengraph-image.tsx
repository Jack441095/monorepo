import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "KENN | mix review that explains itself, by NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "NITE DSP",
    title: "KENN",
    subtitle: "Understand your mix",
    accent: OG_ACCENT.audio,
  });
}
