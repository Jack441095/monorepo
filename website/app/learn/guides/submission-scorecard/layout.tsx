import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Is Your Submission Ready?",
  description:
    "A free interactive scorecard for students. Answer 8 questions and find out if your coursework is ready to submit.",
  path: "/learn/guides/submission-scorecard",
});

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
