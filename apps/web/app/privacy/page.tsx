import Link from "next/link";
import Logo from "@/components/Logo";

export const metadata = {
  title: "Privacy Policy — TweakHub",
};

/**
 * Template Privacy Policy — NOT legal advice. See the notice at the top
 * of the rendered page. Data flows described here are drawn directly
 * from the actual codebase (models/user.py, models/organization.py,
 * services/payment_service.py, services/storage_service.py,
 * services/credit_service.py, config.py's file_retention_hours) rather
 * than generic boilerplate — if that code changes, this doc needs to
 * change with it, particularly the "what we collect" and "how long we
 * keep it" sections.
 */
export default function PrivacyPage() {
  return (
    <main className="legal-doc">
      <Link href="/" style={{ display: "inline-block", marginBottom: 32 }}>
        <Logo size={28} />
      </Link>
      <h1>Privacy Policy</h1>
      <p className="legal-updated">Last updated: 4 September 2026</p>

      <div className="legal-notice">
        <strong>Before this goes live:</strong> this is a starting template, not
        a finished legal document, and has not been reviewed by a lawyer. It
        assumes South Africa as TweakHub&rsquo;s primary jurisdiction (POPIA)
        with GDPR provisions for EU users, since that&rsquo;s what
        docs/tweakhub-master-plan.md&rsquo;s compliance checklist names — confirm
        that&rsquo;s correct, fill in the bracketed placeholders (registered
        entity, Information Officer contact, physical address), and have this
        reviewed by an attorney before relying on it. If TweakHub has users in
        Nigeria, Kenya, or other countries with their own data protection
        laws (plausible given the mobile money coverage below), those laws
        may impose additional obligations this document doesn&rsquo;t yet
        cover.
      </div>

      <h2>1. Who we are</h2>
      <p>
        This Privacy Policy explains how{" "}
        <span data-placeholder>[Registered Company Name]</span>{" "}
        (&ldquo;TweakHub,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;), trading as
        TweakHub at tweakhub.co.za, collects, uses, and protects your personal
        information when you use our service. We are the &ldquo;responsible
        party&rdquo; under South Africa&rsquo;s Protection of Personal
        Information Act, 2013 (POPIA) and, where it applies to you, the
        &ldquo;data controller&rdquo; under the EU General Data Protection
        Regulation (GDPR).
      </p>
      <p>
        Our Information Officer (POPIA) / EU representative (GDPR) can be
        reached at{" "}
        <a href="mailto:privacy@tweakhub.co.za">privacy@tweakhub.co.za</a>,{" "}
        <span data-placeholder>[registered address]</span>.
      </p>

      <h2>2. What we collect</h2>
      <h3>Account information</h3>
      <p>
        Email address, full name, password (stored as a salted hash — we
        never store or can see your plain-text password), country, and, if
        you sign up through Google, the profile information Google shares
        with us for that. If you join or create a Team/Business account, we
        also hold your organization membership and role.
      </p>
      <h3>Files you process</h3>
      <p>
        The files you upload to run a tool, and the files that tool
        generates. These are encrypted at rest and automatically deleted
        after 48 hours by default (see &ldquo;How long we keep it&rdquo;
        below) — we do not manually review, read, or use file contents for
        any purpose other than running the specific operation you requested.
      </p>
      <h3>Payment information</h3>
      <p>
        For card and mobile money payments, your card/mobile money details
        are entered directly on DPO Group&rsquo;s own hosted payment page —
        TweakHub never receives, sees, or stores your full card number, CVV,
        or mobile money PIN. We keep a record of the transaction itself
        (amount, status, a DPO-issued transaction token, and your billing
        reference) but not the underlying payment instrument. For direct
        bank transfers, we keep the reference number and amount needed to
        match your payment.
      </p>
      <h3>Usage and technical data</h3>
      <p>
        Which tools you run, when, and their credit cost; your IP address
        (used for rate-limiting and fraud prevention — see our{" "}
        <Link href="/terms">Terms of Service</Link>); basic device/browser
        information from standard web request headers. We do not currently
        run analytics or advertising cookies/trackers of any kind — if that
        changes, this section and our cookie practices will be updated
        first, with a way to opt out where required by law.
      </p>
      <h3>Referral data</h3>
      <p>
        If you use or are referred through our referral program, we store
        the referral code and which account it&rsquo;s tied to.
      </p>

      <h2>3. Why we process it (lawful basis)</h2>
      <ul>
        <li>
          <strong>To provide the service</strong> — account creation, running
          tools you request, delivering results, billing (necessary to
          perform our contract with you).
        </li>
        <li>
          <strong>Security and fraud prevention</strong> — rate limiting,
          detecting abuse (our legitimate interest, balanced against your
          rights).
        </li>
        <li>
          <strong>Legal compliance</strong> — tax/financial recordkeeping,
          responding to lawful requests from authorities.
        </li>
        <li>
          <strong>With your consent</strong> — for anything not covered
          above (e.g. marketing email, if we ever add it), which
          you can withdraw at any time.
        </li>
      </ul>

      <h2>4. How long we keep it</h2>
      <p>
        <strong>Files:</strong> uploaded inputs and generated outputs are
        deleted automatically after 48 hours by default (configurable per
        deployment — <span data-placeholder>[confirm current production
        value]</span>). Deletion is enforced by a scheduled cleanup job, not
        immediately on the object store itself, so a file may briefly
        persist past that window before the next cleanup run.
      </p>
      <p>
        <strong>Account data:</strong> kept for as long as your account is
        active, plus a reasonable period after closure to comply with legal,
        tax, and dispute-resolution obligations, after which it&rsquo;s
        deleted or anonymized.
      </p>
      <p>
        <strong>Payment records:</strong> transaction records (not payment
        instrument details, which we never hold) are kept as required by
        South African tax and financial recordkeeping law.
      </p>

      <h2>5. Who we share it with</h2>
      <ul>
        <li>
          <strong>DPO Group</strong> — payment processing (card, mobile
          money).
        </li>
        <li>
          <strong>Our hosting/infrastructure providers</strong> — to run the
          servers, database, and storage that operate the service.
        </li>
        <li>
          <strong>Law enforcement or regulators</strong> — only where
          legally required.
        </li>
      </ul>
      <p>
        We do not sell your personal information, and we do not share file
        contents with anyone except as needed to run the tool you requested.
      </p>

      <h2>6. International transfers</h2>
      <p>
        TweakHub&rsquo;s tools are used across multiple African countries
        (our payment methods alone span mobile money providers operating in
        many of them — MTN Mobile Money, Airtel Money, Orange Money, M-Pesa,
        and Wave), and our infrastructure may be hosted outside your own
        country. Where we transfer personal information across borders —
        including to the EU/EEA or elsewhere — we do so only where POPIA
        section 72 (or, for EU data, GDPR&rsquo;s transfer rules, e.g.
        standard contractual clauses) is satisfied, such as an adequate
        level of protection at the destination or your consent.
      </p>

      <h2>7. Your rights</h2>
      <h3>If POPIA applies to you (South Africa)</h3>
      <p>You have the right to:</p>
      <ul>
        <li>Be notified that we hold your personal information, and access it</li>
        <li>Request correction or deletion of information that&rsquo;s inaccurate, irrelevant, excessive, out of date, incomplete, or misleading, or obtained unlawfully</li>
        <li>Object to processing of your information, including for direct marketing</li>
        <li>
          Complain to the Information Regulator (South Africa) if you think
          we&rsquo;ve mishandled your information —{" "}
          <a href="https://inforegulator.org.za" target="_blank" rel="noreferrer">
            inforegulator.org.za
          </a>
        </li>
      </ul>
      <h3>If GDPR applies to you (EU/EEA)</h3>
      <p>
        You additionally have the right to data portability, to restrict
        processing, and to lodge a complaint with your local supervisory
        authority. Where processing is based on consent, you can withdraw it
        at any time without affecting processing already carried out.
      </p>
      <h3>Everyone</h3>
      <p>
        Whatever your jurisdiction, you can ask us to access, correct, or
        delete your personal information, or close your account entirely, by
        emailing{" "}
        <a href="mailto:privacy@tweakhub.co.za">privacy@tweakhub.co.za</a>. If
        your country has its own data protection law that gives you
        additional rights beyond what&rsquo;s listed here, those rights apply
        too and we&rsquo;ll honor a valid request made under them.
      </p>

      <h2>8. Security</h2>
      <p>
        Files are encrypted at rest (AES-based encryption, whichever storage
        backend is in use), passwords are stored as salted hashes never in
        plain text, and access to the service requires an authentication
        token that expires. We restrict internal access to personal
        information to what&rsquo;s needed to operate the service. No system
        is perfectly secure, and we can&rsquo;t guarantee absolute security —
        if we become aware of a breach affecting your personal information,
        we&rsquo;ll notify affected users and, where required, the
        Information Regulator or relevant supervisory authority, within the
        timeframe the law requires.
      </p>

      <h2>9. Children</h2>
      <p>
        TweakHub is not directed at children and we do not knowingly collect
        personal information from anyone under the age of majority in their
        country without appropriate consent. If you believe a child has
        provided us with personal information, contact us and we&rsquo;ll
        delete it.
      </p>

      <h2>10. Changes to this policy</h2>
      <p>
        We may update this Privacy Policy from time to time. We&rsquo;ll post
        the updated version here with a new &ldquo;Last updated&rdquo; date,
        and for material changes we&rsquo;ll make a reasonable effort to
        notify you before they take effect.
      </p>

      <h2>11. Contact</h2>
      <p>
        Questions, or to exercise any right above:{" "}
        <a href="mailto:privacy@tweakhub.co.za">privacy@tweakhub.co.za</a>{" "}
        <span data-placeholder>[confirm this inbox exists and is monitored]</span>.
      </p>
    </main>
  );
}
