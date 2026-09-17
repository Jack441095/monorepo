import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "Is Your Submission Ready? | NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "FREE TOOL",
    title: "Is your submission ready?",
    subtitle: "Interactive scorecard for students",
    accent: OG_ACCENT.workflow,
  });
}
