import { OG_ACCENT, OG_CONTENT_TYPE, OG_SIZE, ogCard } from "@/lib/og";

export const alt = "NITE Files | C++ library folder cleaner by NITE DSP";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function OpengraphImage() {
  return ogCard({
    eyebrow: "NITE DSP",
    title: "NITE Files",
    subtitle: "C++ Library Folder Cleaner",
    accent: OG_ACCENT.files,
  });
}
