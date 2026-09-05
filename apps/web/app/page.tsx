"use client";

import { useEffect, useState } from "react";
import AuthPanel from "@/components/AuthPanel";
import CreditBalance from "@/components/CreditBalance";
import CreditPackages from "@/components/CreditPackages";
import Logo from "@/components/Logo";
import OrganizationCard from "@/components/OrganizationCard";
import ReferralCard from "@/components/ReferralCard";
import ToolRouter from "@/components/ToolRouter";
import { JobResult } from "@/lib/api";

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
    <main className="container" style={{ paddingTop: 40, paddingBottom: 80 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, marginBottom: 40 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Logo size={40} />
          <div>
            <h1 style={{ margin: 0, fontSize: 28 }}>TweakHub</h1>
            <p style={{ margin: "4px 0 0", color: "var(--text-muted)" }}>
              200+ file tools for Africa — PDF, image, video, audio, documents.
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <CreditBalance token={token} />
          {token ? (
            <button
              onClick={() => setToken(null)}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)" }}
            >
              Sign out
            </button>
          ) : (
            <AuthPanel onAuthenticated={setToken} />
          )}
        </div>
      </header>

      {oauthError && (
        <p style={{ color: "var(--danger)", fontSize: 13, marginTop: -24, marginBottom: 24 }}>
          Google sign-in didn&apos;t go through — please try again.
        </p>
      )}
      {pendingInviteToken && !token && (
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: -24, marginBottom: 24 }}>
          You&apos;ve been invited to join a team — sign in or create an account with the email the
          invite was sent to, and it&apos;ll be accepted automatically.
        </p>
      )}

      <section style={{ marginBottom: 48 }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Tools</h2>
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
          <pre
            style={{
              marginTop: 16,
              padding: 16,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              fontSize: 12,
              overflowX: "auto",
            }}
          >
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Buy credits</h2>
        <CreditPackages token={token} />
      </section>

      {token && (
        <section style={{ marginTop: 48 }}>
          <h2 style={{ fontSize: 18, marginBottom: 16 }}>Refer a friend</h2>
          <ReferralCard token={token} />
        </section>
      )}

      {token && (
        <section style={{ marginTop: 48 }}>
          <h2 style={{ fontSize: 18, marginBottom: 16 }}>Team</h2>
          <OrganizationCard
            token={token}
            pendingInviteToken={pendingInviteToken}
            onInviteHandled={() => setPendingInviteToken(null)}
          />
        </section>
      )}

      <footer style={{ marginTop: 64, fontSize: 12, color: "var(--text-muted)" }}>
        <a href="/reset-password" style={{ color: "inherit" }}>
          Forgot your password?
        </a>
      </footer>
    </main>
  );
}
