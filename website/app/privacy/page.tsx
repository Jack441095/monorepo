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
      <p><strong>Last updated:</strong> September 2026</p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Who we are</h2>
      <p>
        NITE DSP is operated by Jack Knowlton as a sole trader based in the United Kingdom.
        For privacy questions, contact{" "}
        <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">What our products do locally</h2>
      <p>
        NITE Submit, SLO, and KENN all process your files entirely on your Mac.
        Documents, audio samples, and mix sessions never leave your machine.
        No file content is uploaded, transmitted, or stored on our servers.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data we collect</h2>
      <p>We collect data only when you actively give it to us:</p>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li><strong>Waitlist sign-ups:</strong> email address, name (optional), qualifying answers (e.g. library size, DAW preference), and any free-text notes you add. Stored in our database to notify you when beta access is ready.</li>
        <li><strong>Account creation:</strong> email address, used to send a magic sign-in link and manage licences. No password is stored.</li>
        <li><strong>Purchases:</strong> handled by Paddle as Merchant of Record. Paddle collects payment details on their own infrastructure. We receive a transaction record (product, amount, email) but never see your card number.</li>
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
        <li>To send a nurture email sequence after you join a waitlist (you can unsubscribe from any email)</li>
        <li>To deliver licence keys and account services</li>
        <li>To respond to support requests</li>
      </ul>
      <p className="mt-2">We do not sell, rent, or share your data with third parties for marketing purposes.</p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data storage and security</h2>
      <p>
        Waitlist and account data is stored in a Neon PostgreSQL database hosted in the EU (Frankfurt).
        The website is hosted on Vercel. All connections use TLS encryption.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Data retention</h2>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li><strong>Waitlist data:</strong> kept until the product launches and you either convert to a customer or ask to be removed.</li>
        <li><strong>Account data:</strong> kept for as long as you have an active licence. Deleted on request.</li>
        <li><strong>Support emails:</strong> kept for 12 months after the last message, then deleted.</li>
      </ul>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Your rights</h2>
      <p>
        You can ask us to show you what data we hold, correct it, or delete it at any time.
        Email <a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a> and
        we will respond within 30 days.
      </p>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Third-party services</h2>
      <ul className="list-disc pl-5 space-y-1 mt-2">
        <li><strong>Paddle:</strong> payment processing (<a href="https://www.paddle.com/legal/privacy" className="underline" target="_blank" rel="noopener">their privacy policy</a>)</li>
        <li><strong>Plausible:</strong> analytics (<a href="https://plausible.io/data-policy" className="underline" target="_blank" rel="noopener">their data policy</a>)</li>
        <li><strong>Vercel:</strong> website hosting</li>
        <li><strong>Neon:</strong> database hosting (EU)</li>
      </ul>

      <h2 className="text-base font-semibold text-foreground mt-6 mb-2">Changes to this policy</h2>
      <p>
        We will update the "last updated" date at the top of this page when changes are made.
        Material changes will be communicated by email to account holders and waitlist members.
      </p>
    </LegalPage>
  );
}
