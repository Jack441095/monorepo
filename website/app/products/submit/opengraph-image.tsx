import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "NITE Submit | document prep intelligence by NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "NITE DSP",
    title: "Submit",
    subtitle: "Document Prep Intelligence",
    accent: OG_ACCENT.workflow,
  });
}
