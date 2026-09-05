import Link from "next/link";
import Logo from "@/components/Logo";

export const metadata = {
  title: "Refund Policy — TweakHub",
};

/**
 * Template Refund/Cancellation Policy — NOT legal advice, see the notice
 * below. The automatic-refund-on-failed-job behavior described here is
 * real (services/credit_service.py::refund_credits(), called from the
 * job worker on a failed ProcessingJob) — keep this accurate to that
 * code if it changes. The cooling-off framing references South Africa's
 * Consumer Protection Act, 2008 s44 (electronic transactions), since
 * that's this app's assumed primary jurisdiction; confirm applicability
 * before relying on it.
 */
export default function RefundPolicyPage() {
  return (
    <main className="legal-doc">
      <Link href="/" style={{ display: "inline-block", marginBottom: 32 }}>
        <Logo size={28} />
      </Link>
      <h1>Refund &amp; Cancellation Policy</h1>
      <p className="legal-updated">Last updated: 4 September 2026</p>

      <div className="legal-notice">
        <strong>Before this goes live:</strong> this is a starting template, not
        a finished legal document, and has not been reviewed by a lawyer.
        Refund rights for consumers are often set by law (not just policy) and
        vary by country — confirm this is accurate for every jurisdiction
        TweakHub actually sells into before relying on it, and have it
        reviewed by an attorney.
      </div>

      <h2>1. Failed tool runs</h2>
      <p>
        If a tool run fails because of an error on TweakHub&rsquo;s side — a
        bug, a crashed background job, a processing engine failure — the
        credits spent on that attempt are refunded to your account balance
        automatically. You don&rsquo;t need to contact support or request
        this; it happens as part of how failures are handled internally.
      </p>
      <p>
        Credits are <strong>not</strong> refunded when a run fails because of
        the input itself — a corrupted, password-protected, unsupported, or
        malformed file, a file that exceeds your plan&rsquo;s size limit, or
        options that don&rsquo;t apply to that file. If you&rsquo;re not sure
        why a run failed, contact support before retrying — we can usually
        tell you what happened.
      </p>
      <p>
        Credits are also not refunded for a technically successful run just
        because you&rsquo;re unhappy with the output quality (for example, a
        compression or conversion result that doesn&rsquo;t look the way
        you expected) — the tools do what they&rsquo;re documented to do; if
        something looks like a genuine bug rather than an unwanted-but-correct
        result, contact support and we&rsquo;ll take a look.
      </p>

      <h2>2. Purchased credits (pay-as-you-go)</h2>
      <p>
        Credit purchases are refundable in cash within{" "}
        <span data-placeholder>[7]</span> days of purchase if you haven&rsquo;t
        spent any of the credits from that purchase yet. Once any credit from
        a purchase has been spent, that purchase is no longer eligible for a
        cash refund — the unspent remainder stays in your account balance to
        use later instead.
      </p>
      <p>
        This reflects South Africa&rsquo;s Consumer Protection Act, 2008
        cooling-off allowance for direct-marketing/electronic transactions
        (currently 7 days) — <span data-placeholder>[confirm this is the
        correct period and that it applies to TweakHub&rsquo;s sales
        model]</span>. If you&rsquo;re buying from a country with a longer or
        different legally mandated cooling-off period, that period applies
        instead where it gives you more protection.
      </p>

      <h2>3. Subscriptions</h2>
      <p>
        You can cancel a subscription plan at any time from your account
        settings. Cancelling stops future renewal charges — it does not
        refund the current billing period, and your plan (and any
        included monthly credits) stays active until the end of the period
        you&rsquo;ve already paid for.
      </p>
      <p>
        If you cancel within <span data-placeholder>[7]</span> days of your
        <em>first</em> subscription charge and haven&rsquo;t meaningfully used
        the plan&rsquo;s included credits, we&rsquo;ll refund that first
        charge — contact support to request it. This first-charge allowance
        doesn&rsquo;t apply to subsequent renewal charges.
      </p>

      <h2>4. Direct bank transfer payments</h2>
      <p>
        If you paid by direct bank transfer and credits were never applied to
        your account (for example, the reference number couldn&rsquo;t be
        matched, or you sent the wrong amount), contact support with your
        proof of payment and we&rsquo;ll either apply the correct credit
        amount or refund the payment to the originating account.
      </p>

      <h2>5. Team/Business account cancellation</h2>
      <p>
        Cancelling a Team or Business plan follows the same subscription
        rules above, applied to the organization&rsquo;s billing owner. Unused
        credits pooled at the organization level are handled the same way as
        an individual account&rsquo;s unused credits.
      </p>

      <h2>6. How to request a refund</h2>
      <p>
        Email{" "}
        <a href="mailto:billing@tweakhub.co.za">billing@tweakhub.co.za</a>{" "}
        <span data-placeholder>[confirm this inbox exists and is monitored]</span>{" "}
        with your account email and the transaction in question. We aim to
        respond within <span data-placeholder>[X]</span> business days.
        Approved refunds are returned to the original payment method where
        possible; for mobile money or bank transfer payments, this may take
        longer than a card refund depending on the provider.
      </p>

      <p>
        This policy works alongside, and doesn&rsquo;t limit, any refund or
        cancellation right you have under mandatory consumer protection law
        in your country, which always takes priority where it gives you more
        than this policy does. See our{" "}
        <Link href="/terms">Terms of Service</Link> for the rest of the
        billing terms.
      </p>
    </main>
  );
}
