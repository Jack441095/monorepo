import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { DownloadRouter } from "@/components/DownloadRouter";

export const metadata: Metadata = pageMetadata({
  title: "Download",
  description: "Download your NITE DSP software. Sign in to reach your licences and builds.",
  path: "/download",
});

export default function DownloadPage() {
  return (
    <>
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Downloads</span>
          <h1 className="section-title mt-4 text-foreground">Get your software.</h1>
          <p className="body-large mt-6">
            Builds are tied to your account. Sign in to see your licences and download the latest
            version for your platform.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container" style={{ maxWidth: "42rem" }}>
          <DownloadRouter />
          <p className="mt-8 text-xs text-muted-dim leading-relaxed">
            No licence yet?{" "}
            <Link href="/beta" className="text-link">Request beta access</Link> or read{" "}
            <Link href="/trust" className="text-link">how we handle your data</Link>. Beta builds
            are delivered through your invitation email and this account area.
          </p>
        </div>
      </section>
    </>
  );
}
