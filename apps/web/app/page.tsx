"use client";

import { useEffect, useState } from "react";
import AuthPanel from "@/components/AuthPanel";
import CreditBalance from "@/components/CreditBalance";
import CreditPackages from "@/components/CreditPackages";
import Logo from "@/components/Logo";
import OrganizationCard from "@/components/OrganizationCard";
import ReferralCard from "@/components/ReferralCard";
import ToolRouter from "@/components/ToolRouter";
import {
  IconArrowRight,
  IconBolt,
  IconClock,
  IconConvert,
  IconGlobe,
  IconShield,
  IconWallet,
} from "@/components/icons/Icons";
import { JobResult } from "@/lib/api";

const FORMAT_CHIPS = ["PDF", "JPG", "MP4", "MP3", "DOCX", "PNG"];

const TRUST_ITEMS = [
  { icon: IconShield, title: "Encrypted at rest", body: "Every file is encrypted the moment it lands, then auto-deleted within 24–48 hours." },
  { icon: IconBolt, title: "Real engines, no queue anxiety", body: "Heavier jobs run on a background worker so a big video never blocks the tab." },
  { icon: IconWallet, title: "Pay the African way", body: "Card, MTN & Airtel Money, M-Pesa, Orange Money, Wave, or a direct bank transfer." },
  { icon: IconGlobe, title: "Credits, not subscriptions", body: "Buy once, use whenever — credits never expire and never lose value to a plan you forgot." },
];

const STEPS = [
  { n: "01", title: "Pick a tool", body: "Search or browse 207 tools across PDF, image, video, audio and document." },
  { n: "02", title: "Drop your file", body: "Add the file (and a second one, for tools like merge or compare) — nothing leaves your session until you say go." },
  { n: "03", title: "Download the result", body: "Most tools finish in seconds; heavier ones process in the background and notify you." },
];

const STATS = [
  { value: "207", label: "tools, and counting" },
  { value: "5", label: "categories covered" },
  { value: "24–48h", label: "auto-delete window" },
  { value: "7", label: "payment rails" },
];

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{ tool: string; summary: Record<string, unknown> } | null>(
    null
  );
  const [oauthError, setOauthError] = useState(false);
  // A team invite link (`?invite_token=...`) — held here until the user
  // is signed in (they may need to create an account with the invited
  // email first), then handed to OrganizationCard to accept and cleared.
  const [pendingInviteToken, setPendingInviteToken] = useState<string | null>(null);

  // Picked up after a round trip through GET /api/auth/google/login ->
  // Google -> GET /api/auth/google/callback, which redirects the browser
  // back here with one of these two query params (never both) — see
  // routes/auth.py's google_callback. Read via window.location rather
  // than next/navigation's useSearchParams for the same reason
  // AuthPanel's ?ref= handling does: avoids forcing a Suspense boundary
  // onto this page just for a client-only, one-time redirect param.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthToken = params.get("oauth_token");
    const hadError = params.get("oauth_error");
    const inviteToken = params.get("invite_token");
    if (oauthToken) {
      // window.location is only available client-side, so this can't move
      // to a lazy useState initializer without an SSR hydration mismatch.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setToken(oauthToken);
    } else if (hadError) {
      setOauthError(true);
    }
    if (inviteToken) {
      setPendingInviteToken(inviteToken);
    }
    if (oauthToken || hadError || inviteToken) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  return (
    <>
      <header
        className="glass-header"
        style={{ position: "sticky", top: 0, zIndex: 40 }}
      >
        <div
          className="container-wide"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 16,
            paddingTop: 16,
            paddingBottom: 16,
          }}
        >
          <a href="#top" style={{ display: "flex" }}>
            <Logo size={34} />
          </a>

          <nav
            style={{
              display: "flex",
              alignItems: "center",
              gap: 28,
              fontSize: 14.5,
              fontWeight: 600,
              color: "var(--text-muted)",
            }}
            className="header-nav"
          >
            <a href="#tools">Tools</a>
            <a href="#pricing">Pricing</a>
            <a href="#how-it-works">How it works</a>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <CreditBalance token={token} />
            {token ? (
              <button onClick={() => setToken(null)} className="btn btn-ghost btn-sm">
                Sign out
              </button>
            ) : (
              <AuthPanel onAuthenticated={setToken} />
            )}
          </div>
        </div>
      </header>

      <main id="top">
        {oauthError && (
          <div className="container-wide" style={{ paddingTop: 16 }}>
            <p style={{ color: "var(--danger)", fontSize: 13.5 }}>
              Google sign-in didn&apos;t go through — please try again.
            </p>
          </div>
        )}
        {pendingInviteToken && !token && (
          <div className="container-wide" style={{ paddingTop: 16 }}>
            <p style={{ color: "var(--text-muted)", fontSize: 13.5 }}>
              You&apos;ve been invited to join a team — sign in or create an account with the email the
              invite was sent to, and it&apos;ll be accepted automatically.
            </p>
          </div>
        )}

        {/* ---------------------------------------------------------- Hero */}
        <section className="container-wide section" style={{ paddingTop: 56 }}>
          <div className="hero-grid">
            <div className="fade-up">
              <span className="eyebrow">
                <IconGlobe size={14} /> Built for Africa · 207 tools live
              </span>
              <h1
                style={{
                  fontSize: "clamp(38px, 5.4vw, 68px)",
                  marginTop: 20,
                  marginBottom: 22,
                }}
              >
                Every file,
                <br />
                <span className="accent-text">any format you need.</span>
              </h1>
              <p style={{ fontSize: 18, color: "var(--text-muted)", maxWidth: 480, marginBottom: 32 }}>
                PDF, image, video, audio and document tools in one place — real processing engines,
                not a waitlist. Pay with card, mobile money or a bank transfer, and only for what you
                use.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginBottom: 40 }}>
                <a href="#tools" className="btn btn-primary">
                  Browse the tools <IconArrowRight size={16} />
                </a>
                <a href="#pricing" className="btn btn-secondary">
                  See credit pricing
                </a>
              </div>
              <div className="hero-trust-row">
                {TRUST_ITEMS.slice(0, 3).map((item) => (
                  <div key={item.title} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <item.icon size={17} color="var(--accent-2)" />
                    <span style={{ fontSize: 13.5, color: "var(--text-muted)", fontWeight: 600 }}>
                      {item.title}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="hero-visual fade-up" style={{ animationDelay: "0.12s" }}>
              <div className="hero-card card" style={{ position: "relative" }}>
                <span className="eyebrow" style={{ color: "var(--text-dim)" }}>
                  Input
                </span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "14px 0 26px" }}>
                  {FORMAT_CHIPS.map((f, i) => (
                    <span
                      key={f}
                      className="format-chip"
                      style={{
                        background: i === 0 ? "var(--accent-fill)" : "var(--surface-2)",
                        color: i === 0 ? "var(--on-accent)" : "var(--text-muted)",
                      }}
                    >
                      {f}
                    </span>
                  ))}
                </div>

                <div style={{ display: "flex", justifyContent: "center", padding: "18px 0" }}>
                  <div className="convert-badge float-slow">
                    <IconConvert size={30} color="var(--on-accent)" strokeWidth={1.8} />
                  </div>
                </div>

                <span className="eyebrow" style={{ color: "var(--text-dim)", marginTop: 6 }}>
                  Output
                </span>
                <div
                  style={{
                    marginTop: 14,
                    padding: "14px 16px",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: 14 }}>optimized-file.pdf</span>
                  <span style={{ fontSize: 12.5, color: "var(--success)", fontWeight: 700 }}>Ready</span>
                </div>

                <div className="float-badge float-badge-a float-slow">
                  <IconShield size={14} color="var(--accent-2)" /> Encrypted
                </div>
                <div className="float-badge float-badge-b float-slow" style={{ animationDelay: "1.4s" }}>
                  <IconClock size={14} color="var(--accent)" /> ~4s avg. runtime
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------- Stats */}
        <section className="section-tight" style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", background: "var(--bg-soft)" }}>
          <div className="container-wide stats-row">
            {STATS.map((s) => (
              <div key={s.label}>
                <div className="tabular-nums" style={{ fontFamily: "var(--font-display)", fontSize: 34, fontWeight: 600 }}>
                  {s.value}
                </div>
                <div style={{ fontSize: 13.5, color: "var(--text-muted)", marginTop: 4 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------ How it works */}
        <section id="how-it-works" className="container-wide section">
          <SectionHeading eyebrow="The flow" title="Three steps. No install." />
          <div className="steps-grid">
            {STEPS.map((step) => (
              <div key={step.n} className="card" style={{ padding: 28 }}>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 13,
                    color: "var(--accent)",
                    fontWeight: 600,
                    marginBottom: 14,
                  }}
                >
                  {step.n}
                </div>
                <h3 style={{ fontSize: 19, marginBottom: 8, fontWeight: 600 }}>{step.title}</h3>
                <p style={{ fontSize: 14.5, color: "var(--text-muted)", margin: 0 }}>{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------------ Tools */}
        <section id="tools" className="container-wide section" style={{ paddingTop: 0 }}>
          <SectionHeading
            eyebrow="The catalog"
            title="Every tool, in one place"
            body="Pick a category, choose a tool, and drop your file — most jobs finish in seconds."
          />
          <ToolRouter
            token={token}
            onRun={(tool, result: JobResult) =>
              setLastResult({
                tool,
                summary: {
                  status: result.status,
                  isAsync: result.isAsync,
                  contentType: result.contentType,
                  creditsSpent: result.creditsSpent,
                  creditBalance: result.creditBalance,
                  expiresAt: result.expiresAt,
                  ...result.meta,
                },
              })
            }
          />
          {lastResult && (
            <details style={{ marginTop: 20 }}>
              <summary style={{ cursor: "pointer", fontSize: 12.5, color: "var(--text-dim)", fontWeight: 600 }}>
                Last run details
              </summary>
              <pre
                style={{
                  marginTop: 10,
                  padding: 16,
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  overflowX: "auto",
                  color: "var(--text-muted)",
                }}
              >
                {JSON.stringify(lastResult, null, 2)}
              </pre>
            </details>
          )}
        </section>

        {/* ----------------------------------------------------------- Trust */}
        <section className="section-tight" style={{ background: "var(--bg-soft)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
          <div className="container-wide trust-grid">
            {TRUST_ITEMS.map((item) => (
              <div key={item.title} style={{ display: "flex", gap: 14 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 11,
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    color: "var(--accent-2)",
                  }}
                >
                  <item.icon size={19} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>{item.title}</div>
                  <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>{item.body}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------------- Pricing */}
        <section id="pricing" className="container-wide section">
          <SectionHeading
            eyebrow="Credits"
            title="Pay as you go"
            body="Buy a credit pack once — no subscription, no expiry — and spend it on whichever tool you need, whenever you need it."
          />
          <CreditPackages token={token} />
        </section>

        {token && (
          <section className="container-wide section-tight">
            <SectionHeading eyebrow="Grow" title="Refer a friend" />
            <ReferralCard token={token} />
          </section>
        )}

        {token && (
          <section className="container-wide section-tight">
            <SectionHeading eyebrow="Business" title="Your team" />
            <OrganizationCard
              token={token}
              pendingInviteToken={pendingInviteToken}
              onInviteHandled={() => setPendingInviteToken(null)}
            />
          </section>
        )}
      </main>

      <footer style={{ borderTop: "1px solid var(--border)", marginTop: 40 }}>
        <div
          className="container-wide"
          style={{
            paddingTop: 48,
            paddingBottom: 40,
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            gap: 24,
          }}
        >
          <div style={{ maxWidth: 320 }}>
            <Logo size={28} />
            <p style={{ fontSize: 13.5, color: "var(--text-muted)", marginTop: 14 }}>
              200+ file tools for Africa — PDF, image, video, audio and document, in one place.
              TweakHub is a subsidiary of OnPoint CRM.
            </p>
          </div>
          <div style={{ display: "flex", gap: 56, flexWrap: "wrap" }}>
            <FooterColumn title="Product" links={[{ label: "Tools", href: "#tools" }, { label: "Pricing", href: "#pricing" }]} />
            <FooterColumn title="Account" links={[{ label: "Forgot your password?", href: "/reset-password" }]} />
          </div>
        </div>
        <div
          className="container-wide"
          style={{
            borderTop: "1px solid var(--border)",
            paddingTop: 18,
            paddingBottom: 24,
            fontSize: 12.5,
            color: "var(--text-dim)",
          }}
        >
          © {new Date().getFullYear()} TweakHub. Files are encrypted at rest and auto-deleted within 24–48 hours.
        </div>
      </footer>
    </>
  );
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body?: string }) {
  return (
    <div style={{ marginBottom: 40, maxWidth: 560 }}>
      <span className="eyebrow">{eyebrow}</span>
      <h2 style={{ fontSize: "clamp(26px, 3.4vw, 38px)", marginTop: 14, marginBottom: body ? 12 : 0 }}>
        {title}
      </h2>
      {body && <p style={{ fontSize: 15.5, color: "var(--text-muted)", margin: 0 }}>{body}</p>}
    </div>
  );
}

function FooterColumn({ title, links }: { title: string; links: { label: string; href: string }[] }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 14 }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {links.map((l) => (
          <a key={l.label} href={l.href} style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
            {l.label}
          </a>
        ))}
      </div>
    </div>
  );
}
