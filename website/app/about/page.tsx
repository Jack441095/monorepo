import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = pageMetadata({
  title: "About",
  description: "NITE DSP is built by Jack Knowlton, an audio engineer turned developer with 12 years in studios, game audio, and AI audio systems.",
  path: "/about",
});

export default function AboutPage() {
  return (
    <>
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow text-brand-blue-bright">About</span>
          <h1 className="section-title mt-4 text-foreground">Built by someone who uses the tools.</h1>
          <p className="body-large mt-6">
            NITE DSP started because the tools I needed didn&apos;t exist yet.
          </p>
        </div>
      </section>

      <section className="section section-rule">
        <div className="site-container" style={{ maxWidth: "42rem" }}>
          <Reveal>
            <div className="prose-custom">
              <p>
                I&apos;m Jack Knowlton. I&apos;ve spent the last 12 years working with audio in one form or another. I started in recording studios, then moved into game audio and interactive sound design using tools like Ableton Live and Wwise. Eventually I started writing code to solve problems that existing software couldn&apos;t.
              </p>
              <p>
                That led me into building audio coding systems, AI-driven audio tools, and eventually NITE DSP.
              </p>

              <h2>Why I&apos;m building this</h2>
              <p>
                I had tens of thousands of samples across hundreds of folders and I could never find what I was looking for. Every search tool relied on filenames or tags, which were usually wrong or missing entirely. I wanted to search by how something sounds, not by what someone decided to call it three years ago.
              </p>
              <p>
                So I built SLO. It analyses the acoustic properties of each sample and lets you find similar sounds based on the actual signal. No tags, no renaming, no reorganising. Just audio in, results out.
              </p>
              <p>
                Submit came from a similar frustration. I kept running into the same problem with document preparation: checking naming conventions, verifying metadata, packaging files correctly. It was repetitive work that a machine should handle, but every existing tool either required cloud uploads or tried to do too much. I wanted something that just checks and prepares, locally, without touching the originals.
              </p>

              <h2>The local-first thing</h2>
              <p>
                Every NITE DSP tool runs entirely on your machine. Nothing gets uploaded. Your audio files, your documents, your creative work stays on your hard drive. That&apos;s not a marketing angle. It&apos;s a design principle.
              </p>
              <p>
                I&apos;ve seen too many tools disappear when a company changes direction or shuts down a service. If you buy a NITE DSP product, it works as long as your Mac does. No subscription, no server dependency, no surprises.
              </p>

              <h2>Where this is going</h2>
              <p>
                Right now I&apos;m focused on getting SLO, Submit, and KENN into the hands of the first 50 beta testers each. KENN is an AI audio assistant that lives inside Ableton Live. It listens to your mix, explains what it hears, and helps you make better decisions. All three waitlists are open and the feedback will shape what ships.
              </p>
              <p>
                If any of this sounds useful to you, I&apos;d genuinely love to hear from you. Join a waitlist, drop me a line through the support page, or just have a look around.
              </p>

              <div className="mt-10 flex flex-wrap gap-4">
                <Link href="/products" className="btn-primary">
                  See the products
                </Link>
                <Link href="/support" className="btn-secondary">
                  Get in touch
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
