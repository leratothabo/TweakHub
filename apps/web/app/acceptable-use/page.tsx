import Link from "next/link";
import Logo from "@/components/Logo";

export const metadata = {
  title: "Acceptable Use Policy — TweakHub",
};

/**
 * Template Acceptable Use Policy — NOT legal advice, see the notice
 * below. Referenced from Terms of Service (Section 6) as part of that
 * agreement, and from Privacy Policy re: automated-processing-only /
 * no manual file review.
 */
export default function AcceptableUsePage() {
  return (
    <main className="legal-doc">
      <Link href="/" style={{ display: "inline-block", marginBottom: 32 }}>
        <Logo size={28} />
      </Link>
      <h1>Acceptable Use Policy</h1>
      <p className="legal-updated">Last updated: 4 September 2026</p>

      <div className="legal-notice">
        <strong>Before this goes live:</strong> this is a starting template, not
        a finished legal document, and has not been reviewed by a lawyer. This
        policy is part of our <Link href="/terms">Terms of Service</Link>.
      </div>

      <h2>1. What this covers</h2>
      <p>
        This policy applies to everything you upload, process, or generate
        through TweakHub, and to how you interact with the service itself
        (the app, our API, and our infrastructure). Violating it is a breach
        of our <Link href="/terms">Terms of Service</Link> and can result in
        content removal, credit forfeiture, or account suspension or
        termination, without refund, depending on severity.
      </p>
      <p>
        Automated tools process your files without manual review — but that
        doesn&rsquo;t mean anything goes. You&rsquo;re responsible for what
        you upload, and violations we do become aware of (through automated
        detection, abuse reports, or legal process) are acted on.
      </p>

      <h2>2. Never permitted, no exceptions</h2>
      <p>
        <strong>
          Content that sexualizes, exploits, or endangers a minor — including
          AI-generated or otherwise fictional depictions — is never permitted
          under any circumstance.
        </strong>{" "}
        We report any such content we become aware of to the National Center
        for Missing &amp; Exploited Children (NCMEC) and/or the relevant
        authorities in your country, and terminate the associated account
        immediately.
      </p>
      <p>The same zero-tolerance standard applies to:</p>
      <ul>
        <li>Malware, ransomware, or exploit code intended to cause harm</li>
        <li>Content or activity that facilitates terrorism or targeted violence</li>
        <li>Human trafficking or the non-consensual sexual exploitation of anyone</li>
      </ul>

      <h2>3. Also not permitted</h2>
      <ul>
        <li>
          <strong>Infringing content</strong> — processing files you don&rsquo;t
          have the legal right to use, or that infringe someone else&rsquo;s
          copyright, trademark, or other intellectual property rights
        </li>
        <li>
          <strong>Illegal content</strong> — anything whose creation,
          possession, or distribution is illegal under applicable law
        </li>
        <li>
          <strong>Fraud</strong> — using TweakHub&rsquo;s tools to create
          forged, falsified, or deceptive documents intended to defraud
          someone (fake IDs, altered financial records, forged signatures on
          legal documents, and similar)
        </li>
        <li>
          <strong>Malicious files</strong> — uploading files designed to
          exploit vulnerabilities in TweakHub&rsquo;s own processing engines
          or infrastructure (e.g. crafted files targeting a known CVE in a
          PDF/image/document library)
        </li>
        <li>
          <strong>Privacy violations</strong> — processing someone else&rsquo;s
          personal information without a lawful basis to do so, or using
          TweakHub to compile or dox private information about someone
        </li>
      </ul>

      <h2>4. Abuse of the service itself</h2>
      <ul>
        <li>
          Attempting to bypass rate limits, plan limits, or credit metering
          (including automated scripts designed to evade them)
        </li>
        <li>
          Reverse engineering, scraping, or attempting to extract
          TweakHub&rsquo;s underlying models, processing pipelines, or
          non-public source code
        </li>
        <li>
          Reselling or reproducing TweakHub&rsquo;s service as your own
          product without a separate written agreement with us
        </li>
        <li>
          Security testing (penetration testing, vulnerability scanning)
          against TweakHub&rsquo;s infrastructure without our prior written
          permission — if you&rsquo;ve found a genuine security issue,
          please report it responsibly to{" "}
          <a href="mailto:security@tweakhub.co.za">security@tweakhub.co.za</a>{" "}
          <span data-placeholder>[confirm this inbox exists]</span> instead
        </li>
        <li>
          Using the service in any way that places excessive, abnormal load
          on our infrastructure outside of normal tool usage
        </li>
      </ul>

      <h2>5. Enforcement</h2>
      <p>
        We may remove content, suspend processing, or terminate accounts that
        violate this policy, with or without notice depending on severity.
        Credits spent on a run we later determine violated this policy are
        not refunded. Where content or activity is illegal, we may be
        required to preserve records and report to law enforcement.
      </p>
      <p>
        If you think we&rsquo;ve made a mistake about your account or
        content, contact{" "}
        <a href="mailto:support@tweakhub.co.za">support@tweakhub.co.za</a>{" "}
        <span data-placeholder>[confirm this inbox exists]</span>.
      </p>

      <h2>6. Reporting a violation</h2>
      <p>
        If you believe someone is using TweakHub to process illegal content
        or otherwise violate this policy, report it to{" "}
        <a href="mailto:abuse@tweakhub.co.za">abuse@tweakhub.co.za</a>{" "}
        <span data-placeholder>[confirm this inbox exists]</span>. Include as
        much detail as you can — we take reports seriously and investigate
        promptly.
      </p>
    </main>
  );
}
