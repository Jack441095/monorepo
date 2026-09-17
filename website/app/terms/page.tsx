import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { LegalPage } from "@/lib/legal";
import Link from "next/link";

export const metadata: Metadata = pageMetadata({
  title: "Terms of Service",
  description:
    "Terms covering use of the NITE DSP website, waitlist, and software licences.",
  path: "/terms",
});

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service">
      <p><strong>Last updated:</strong> September 2026</p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Agreement</h2>
      <p>
        By using the NITE DSP website, joining a waitlist, or purchasing a product,
        you agree to these terms. If you do not agree, please do not use our services.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Products and licences</h2>
      <p>
        NITE DSP products (Submit, SLO, KENN) are macOS desktop applications sold as
        perpetual single-user licences. "Perpetual" means you own the version you purchased
        for as long as your Mac runs it. It does not guarantee future updates or new versions.
      </p>
      <p>
        You may install the software on up to two Macs that you personally own and use.
        You may not redistribute, resell, sublicence, or reverse-engineer the software.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Waitlist</h2>
      <p>
        Joining a waitlist reserves your place but does not guarantee access to a product
        or a specific launch date. We may close a waitlist when capacity is reached.
        You can remove yourself from any waitlist by emailing{" "}
        <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Payments and refunds</h2>
      <p>
        Payments are processed by Paddle as Merchant of Record. Paddle handles applicable
        sales tax and issues receipts on our behalf. See our{" "}
        <Link href="/refund-policy" className="underline">refund policy</Link> for details
        on returns.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Beta software</h2>
      <p>
        Beta versions are provided "as is" for testing and feedback purposes.
        They may contain bugs, incomplete features, or breaking changes.
        We are not liable for data loss or other issues arising from beta software use.
        Always keep backups of your important files.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Local processing</h2>
      <p>
        NITE DSP products process your files locally on your Mac. We do not access, view,
        or store the content of your documents, audio files, or mix sessions. You are
        solely responsible for the files you process with our tools.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Limitation of liability</h2>
      <p>
        NITE DSP products are tools, not guarantees. Submit checks file structure but does
        not guarantee that a submission portal will accept your file. SLO classifies audio
        but does not guarantee accuracy. KENN provides mix observations but does not
        replace professional audio engineering judgement.
      </p>
      <p>
        To the maximum extent permitted by law, NITE DSP is not liable for indirect,
        incidental, or consequential damages arising from use of our products or services.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Acceptable use</h2>
      <p>You agree not to:</p>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li>Use our products to violate any law or academic integrity policy</li>
        <li>Attempt to circumvent licence activation or access controls</li>
        <li>Scrape, crawl, or automate access to the NITE DSP website beyond normal use</li>
        <li>Misrepresent your identity when joining a waitlist or purchasing a product</li>
      </ul>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Changes to these terms</h2>
      <p>
        We may update these terms from time to time. Material changes will be communicated
        by email to account holders. Continued use of our services after changes constitutes
        acceptance of the updated terms.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Governing law</h2>
      <p>
        These terms are governed by the laws of England and Wales. Disputes will be subject
        to the exclusive jurisdiction of the courts of England and Wales.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Contact</h2>
      <p>
        Questions about these terms? Email{" "}
        <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>.
      </p>
    </LegalPage>
  );
}
