import Link from "next/link";
import Logo from "@/components/Logo";

export const metadata = {
  title: "Terms of Service — TweakHub",
};

/**
 * Template Terms of Service — NOT legal advice, and not something to
 * launch on as-is. See the "Before this goes live" notice at the top of
 * the rendered page for the specific things that need a real answer
 * (confirmed legal entity name/registration/address) and a lawyer's
 * review (this whole document) before this is relied on for a live,
 * paying userbase. Written to accurately reflect what this codebase
 * actually does today (services/tools_catalog.py's tool list,
 * services/payment_service.py's DPO-hosted card capture + manual bank
 * transfer, services/credit_service.py's refund-on-failed-job behavior,
 * services/storage_service.py's encryption+retention) rather than
 * generic SaaS boilerplate — update this doc if that behavior changes.
 */
export default function TermsPage() {
  return (
    <main className="legal-doc">
      <Link href="/" style={{ display: "inline-block", marginBottom: 32 }}>
        <Logo size={28} />
      </Link>
      <h1>Terms of Service</h1>
      <p className="legal-updated">Last updated: 4 September 2026</p>

      <div className="legal-notice">
        <strong>Before this goes live:</strong> this is a starting template, not a
        finished legal document. It has not been reviewed by a lawyer, and the
        bracketed fields below (company registration details, address, contact
        info) are placeholders — TweakHub&rsquo;s payment records currently
        describe it only as <span data-placeholder>&ldquo;a subsidiary of
        OnPoint CRM&rdquo;</span>, which hasn&rsquo;t been confirmed as the
        correct registered entity. Fill in the real details and have this
        reviewed by an attorney licensed in South Africa (and in any other
        country you operate from) before relying on it.
      </div>

      <h2>1. Who this agreement is with</h2>
      <p>
        These Terms of Service (&ldquo;Terms&rdquo;) are a contract between you
        and{" "}
        <span data-placeholder>[Registered Company Name]</span>, a company
        registered in <span data-placeholder>[South Africa / registration
        number]</span>, with its registered address at{" "}
        <span data-placeholder>[registered address]</span> (&ldquo;TweakHub,&rdquo;
        &ldquo;we,&rdquo; &ldquo;us&rdquo;), trading as TweakHub at
        tweakhub.co.za. By creating an account or using the service, you agree
        to these Terms and to our <Link href="/privacy">Privacy Policy</Link>.
        If you don&rsquo;t agree, don&rsquo;t use TweakHub.
      </p>
      <p>
        If you&rsquo;re using TweakHub on behalf of a company or other legal
        entity (a Team or Business account), you confirm you have authority to
        bind that entity to these Terms, and &ldquo;you&rdquo; refers to that
        entity as well as you personally.
      </p>

      <h2>2. The service</h2>
      <p>
        TweakHub is a file-processing service — PDF, image, video, audio, and
        document conversion and manipulation tools accessed through our web
        app or API. Some tools process your file and return a result
        immediately; others (large video jobs, and tools that run through
        LibreOffice, OCR, or a headless browser) are queued and processed in
        the background — either way, the tool only touches the specific file
        you submit for that one operation.
      </p>
      <p>
        We&rsquo;re constantly adding tools and may change, suspend, or retire
        individual tools or features. We&rsquo;ll try to give notice for
        anything that meaningfully affects paying users, but we don&rsquo;t
        guarantee any specific tool stays available forever.
      </p>

      <h2>3. Accounts</h2>
      <p>
        You need an account to use TweakHub. You&rsquo;re responsible for
        keeping your login credentials confidential and for all activity
        under your account. Tell us right away if you suspect unauthorized
        access. You must be at least the age of majority in your country to
        create an account; TweakHub is not directed at children and we do not
        knowingly collect data from them.
      </p>
      <p>
        You&rsquo;re responsible for the accuracy of the information you give
        us (email, name, country) and for keeping it up to date.
      </p>

      <h2>4. Plans, credits, and billing</h2>
      <p>
        TweakHub is priced through a mix of subscription plans and
        pay-as-you-go credits, described at signup and in your account
        dashboard. Each tool run costs a number of credits based on the tool
        and file size (larger files above a size threshold cost more — see
        your dashboard for current rates); the exact pricing is shown before
        you commit to a paid action and can change with notice.
      </p>
      <p>
        If a tool run fails because of an error on our end (a bug, a crashed
        background job, an engine failure), the credits spent on that attempt
        are automatically refunded to your balance — you don&rsquo;t need to
        ask. Credits are not refunded for a successful run just because
        you&rsquo;re unhappy with the output, or for a failure caused by an
        invalid, corrupted, or unsupported input file. See our{" "}
        <Link href="/refund-policy">Refund Policy</Link> for cash refunds on
        purchased credits and subscriptions.
      </p>
      <p>
        Payment is handled by DPO Group (card and mobile money) or by direct
        bank transfer for manual EFT payments — see Section 9 (Payments) and
        our <Link href="/privacy">Privacy Policy</Link> for how that works.
        Subscriptions renew automatically at the then-current price until you
        cancel; you can cancel anytime from your account settings, effective
        at the end of the current billing period.
      </p>

      <h2>5. Your files and content</h2>
      <p>
        You keep all rights to the files you upload and the files TweakHub
        generates from them. We don&rsquo;t claim ownership, and we don&rsquo;t
        use your files to train models or for any purpose beyond running the
        specific tool you requested and, briefly, making the result available
        for you to download.
      </p>
      <p>
        Uploaded files and results are encrypted at rest and automatically
        deleted after a limited retention window (48 hours by default —
        see <Link href="/privacy">Privacy Policy</Link> for the current
        figure and how deletion actually works). We don&rsquo;t manually
        review file contents; automated processing only.
      </p>
      <p>
        You&rsquo;re solely responsible for the files you upload. You confirm
        you have the right to upload and process them, and that doing so
        doesn&rsquo;t infringe anyone else&rsquo;s rights or break the law.
        See our <Link href="/acceptable-use">Acceptable Use Policy</Link> for
        what&rsquo;s off-limits.
      </p>

      <h2>6. Acceptable use</h2>
      <p>
        Don&rsquo;t use TweakHub to process illegal content, infringe
        intellectual property, distribute malware, or otherwise violate our{" "}
        <Link href="/acceptable-use">Acceptable Use Policy</Link>, which is
        part of these Terms. We may suspend or terminate accounts that
        violate it, and, where required by law, report certain content
        (including any content involving the exploitation of a minor) to the
        relevant authorities.
      </p>

      <h2>7. Referrals and credits programs</h2>
      <p>
        If we offer a referral program, its specific terms (how bonus
        credits are earned, limits, and eligibility) are shown in your
        dashboard and are part of these Terms. We may change or end referral
        programs at any time; changes don&rsquo;t claw back credits
        you&rsquo;ve already earned.
      </p>

      <h2>8. Service availability</h2>
      <p>
        We aim for high uptime but don&rsquo;t guarantee the service will be
        uninterrupted, error-free, or available at all times. Scheduled
        maintenance, third-party outages (our hosting, payment, or engine
        dependencies), or events outside our control may affect availability.
      </p>

      <h2>9. Payments and third parties</h2>
      <p>
        Card and mobile money payments are processed by DPO Group; when you
        pay by card or mobile money, you&rsquo;re redirected to DPO&rsquo;s own
        secure payment page — TweakHub never receives or stores your full
        card number, CVV, or mobile money PIN. Direct bank transfer payments
        are matched manually against the reference number on your invoice.
        Your use of DPO&rsquo;s payment page is also subject to DPO&rsquo;s own
        terms.
      </p>

      <h2>10. Disclaimers and limitation of liability</h2>
      <p>
        TweakHub is provided &ldquo;as is&rdquo; without warranties of any
        kind, to the fullest extent the law allows. We&rsquo;re not liable for
        indirect, incidental, or consequential damages arising from your use
        of the service, including loss of data, profits, or business
        opportunity — except where such liability can&rsquo;t be excluded
        under applicable law (including the Consumer Protection Act, 2008, for
        South African consumers). Our total liability for any claim is
        limited to the amount you paid us in the 3 months before the claim
        arose, or <span data-placeholder>[amount]</span>, whichever is
        greater.
      </p>
      <p>
        Nothing in these Terms limits liability for death or personal injury
        caused by our negligence, fraud, or anything else that can&rsquo;t
        lawfully be limited.
      </p>

      <h2>11. Termination</h2>
      <p>
        You can close your account anytime from your account settings. We may
        suspend or terminate your account for violating these Terms or our{" "}
        <Link href="/acceptable-use">Acceptable Use Policy</Link>, for
        non-payment, or where required by law. Unused purchased credits at
        termination are handled per our{" "}
        <Link href="/refund-policy">Refund Policy</Link>.
      </p>

      <h2>12. Changes to these Terms</h2>
      <p>
        We may update these Terms from time to time. We&rsquo;ll post the
        updated version here with a new &ldquo;Last updated&rdquo; date, and
        for material changes we&rsquo;ll make a reasonable effort to notify
        you (email or an in-app notice) before they take effect. Continuing
        to use TweakHub after a change takes effect means you accept it.
      </p>

      <h2>13. Governing law and disputes</h2>
      <p>
        These Terms are governed by the laws of{" "}
        <span data-placeholder>[South Africa]</span>, without regard to
        conflict-of-law rules. Any dispute will be subject to the exclusive
        jurisdiction of the courts of{" "}
        <span data-placeholder>[South Africa]</span>, except where
        applicable consumer-protection law gives you the right to bring a
        claim in your own country&rsquo;s courts instead.
      </p>

      <h2>14. Contact</h2>
      <p>
        Questions about these Terms:{" "}
        <a href="mailto:legal@tweakhub.co.za">legal@tweakhub.co.za</a>{" "}
        <span data-placeholder>[confirm this inbox exists and is monitored]</span>.
      </p>
    </main>
  );
}
