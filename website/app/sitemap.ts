import type { MetadataRoute } from "next";
import { LEARN_PAGES } from "@/lib/learn";

// Match the canonical host in layout.tsx to avoid duplicate indexed URLs.
const BASE_URL = "https://www.nitedsp.co.uk";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "",
    "/products",
    "/products/submit",
    "/products/smart-sample-manager",
    "/products/kenn",
    "/products/files",
    "/technology",
    "/thursday",
    "/download",
    "/beta",
    "/trust",
    "/pricing",
    "/support",
    "/learn",
    ...LEARN_PAGES.map((p) => `/learn/smart-sample-manager/${p.slug}`),
    "/about",
    "/learn/insights/why-filenames-fail",
    "/learn/insights/acoustic-timbre-search",
    "/learn/insights/local-first-creative-tools",
    "/learn/guides/submission-checklist",
    "/learn/guides/submission-scorecard",
    "/services",
    "/paraphrase",
    "/privacy",
    "/terms",
    "/eula",
    "/refund-policy",
  ];
  // No lastModified on purpose. It used to be `new Date()`, which stamped
  // every URL with the build time — telling crawlers the entire site had
  // just changed on every single deploy. lastModified is optional, and
  // crawlers discount the signal entirely once it is obviously unreliable,
  // so emitting nothing beats emitting something false. Reinstate it only
  // with genuine per-page modification dates.
  return routes.map((route) => ({
    url: `${BASE_URL}${route}`,
  }));
}
