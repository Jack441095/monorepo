import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "Student Submission Checklist | NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "FREE GUIDE",
    title: "The Student Submission Checklist",
    subtitle: "Eight checks before you hit submit",
    accent: OG_ACCENT.workflow,
  });
}
