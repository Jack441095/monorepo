import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { LegalPage } from "@/lib/legal";

export const metadata: Metadata = pageMetadata({
  title: "Privacy Policy",
  description:
    "How NITE DSP handles personal data: local product processing, waitlist data, payment processing, analytics, and your rights.",
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p><strong>Last updated:</strong> October 2026</p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Who we are</h2>
      <p>
        NITE DSP is a product brand operated by a UK limited company. The
        company&apos;s registered name, number, and registered office address are
        being confirmed before purchases reopen.
        For privacy questions, contact{" "}
        <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">What our products do locally</h2>
      <p>
        Submit and SLO process documents and audio locally on your Mac; those apps
        do not upload the files you process to NITE DSP services. Para-phase is an
        online writing service and is not currently enabled. KENN remains in
        research and development and is not offered for sale.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data we collect</h2>
      <p>We collect data only when you actively give it to us:</p>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li><strong>Waitlist sign-ups:</strong> email address, name (optional), qualifying answers (e.g. library size, DAW preference), and any free-text notes you add. Stored in our database to notify you when beta access is ready.</li>
        <li><strong>Account creation:</strong> email address, used to send a magic sign-in link and manage licences. No password is stored.</li>
        <li><strong>Purchases:</strong> processed by Stripe. Stripe collects payment details on their own infrastructure. We receive a transaction record (product, amount, email) but never see your card number.</li>
        <li><strong>Support emails:</strong> whatever you include in your message to nitedsp@outlook.com. We never ask for passwords, payment details, or unredacted personal documents.</li>
      </ul>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Analytics</h2>
      <p>
        We use Plausible Analytics, a privacy-friendly service that does not use cookies,
        does not track individuals, and does not collect personal data.
        It records aggregate page views, referral sources, and country-level location only.
        No cookie banner is needed because no cookies are set.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">How we use your data</h2>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li>To notify you when your waitlist spot opens or beta access is ready</li>
        <li>To deliver licence keys and account services</li>
        <li>To respond to support requests</li>
      </ul>
      <p className="mt-2">We do not sell, rent, or share your data with third parties for marketing purposes.</p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data storage and security</h2>
      <p>
        Waitlist sign-ups are stored separately in Neon. Account, licence, and
        commerce records use the backend database hosted on Fly.io. The website
        runs on Vercel, release downloads use Cloudflare R2, payment processing
        uses Stripe, and transactional email uses Resend. Provider regions and
        data-transfer details are being verified before purchases reopen.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data retention</h2>
      <p>
        We are reviewing retention periods and deletion procedures for each data
        type. Contact{" "}
        <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>
        {" "}to request access to or deletion of your data.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Your rights</h2>
      <p>
        You can ask us to show you what data we hold, correct it, or delete it at any time.
        Email <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a> and
        we will respond within 30 days.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Third-party services</h2>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li><strong>Stripe:</strong> payment processing (<a href="https://stripe.com/privacy" className="underline" target="_blank" rel="noopener">their privacy policy</a>)</li>
        <li><strong>Plausible:</strong> analytics (<a href="https://plausible.io/data-policy" className="underline" target="_blank" rel="noopener">their data policy</a>)</li>
        <li><strong>Vercel:</strong> website hosting</li>
        <li><strong>Neon:</strong> waitlist database hosting</li>
        <li><strong>Fly.io:</strong> backend and account database hosting</li>
        <li><strong>Cloudflare R2:</strong> release file storage</li>
        <li><strong>Resend:</strong> transactional email delivery</li>
      </ul>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Changes to this policy</h2>
      <p>
        We will update the &ldquo;last updated&rdquo; date at the top of this page when changes are made.
        Material changes will be posted on this page.
      </p>
    </LegalPage>
  );
}
