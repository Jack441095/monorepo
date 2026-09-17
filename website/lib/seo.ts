import type { Metadata } from "next";

// Single source of truth for per-page metadata.
//
// Before this existed each page hand-wrote `alternates.canonical` but never an
// `openGraph.url`, so the root layout's homepage URL was inherited by every
// page and every share card pointed at "/". Building both from one `path`
// keeps them from drifting apart again.
//
// www, not the bare apex — see app/sitemap.ts for why.
export const SITE_URL = "https://www.nitedsp.co.uk";
export const SITE_NAME = "NITE DSP";

type PageMetadataInput = {
  /** Page title WITHOUT the "| NITE DSP" suffix; the root template adds it. */
  title: string;
  description: string;
  /** Site-root-relative path, e.g. "/pricing". Used for canonical AND og:url. */
  path: string;
};

export function pageMetadata({ title, description, path }: PageMetadataInput): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      title: `${title} | ${SITE_NAME}`,
      description,
      url: path,
      siteName: SITE_NAME,
      type: "website",
    },
  };
}
