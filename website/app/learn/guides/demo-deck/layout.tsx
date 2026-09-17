import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "NITE DSP Demo Deck",
  description:
    "Presentation deck for university society demos. Overview of Submit, SLO, and KENN.",
  path: "/learn/guides/demo-deck",
});

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
