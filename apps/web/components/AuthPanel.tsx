"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  onAuthenticated: (token: string) => void;
}

type Mode = "login" | "signup";

/** Signup/login form. Calls the real /api/auth endpoints — see docs/TODO.md for what's still stubbed (real email delivery). */
export default function AuthPanel({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Picked up from a shared ?ref=CODE link (see ReferralCard) — read via
  // window.location rather than next/navigation's useSearchParams so this
  // component doesn't force a Suspense boundary onto its page just for a
  // client-only convenience.
  const [referralCode, setReferralCode] = useState<string | null>(null);
  // Only shown once we've confirmed the API has GOOGLE_CLIENT_ID/SECRET
  // configured — otherwise the button would just 501 on click.
  const [googleEnabled, setGoogleEnabled] = useState(false);

  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) {
      // Reading window.location has to happen in an effect (it doesn't
      // exist during this client component's initial server render), so
      // the setState here can't move into a lazy useState initializer
      // without reintroducing a hydration mismatch.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setReferralCode(ref);
      setMode("signup");
    }
    api
      .getGoogleOAuthStatus()
      .then((res) => setGoogleEnabled(res.enabled))
      .catch(() => setGoogleEnabled(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signup") {
        const res = await api.signup(email, password, fullName || undefined, referralCode || undefined);
        setNotice(res.message);
        setMode("login");
      } else {
        const res = await api.login(email, password);
        onAuthenticated(res.access_token);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="auth-panel">
      <input
        type="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        className="auth-input"
      />
      {mode === "signup" && (
        <input
          placeholder="Full name (optional)"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="auth-input"
        />
      )}
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={8}
        className="auth-input"
      />
      <button type="submit" disabled={busy} className="btn btn-primary btn-sm">
        {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
      <button
        type="button"
        onClick={() => {
          setMode(mode === "login" ? "signup" : "login");
          setError(null);
          setNotice(null);
        }}
        className="auth-toggle"
      >
        {mode === "login" ? "Need an account?" : "Have an account?"}
      </button>

      {mode === "signup" && referralCode && (
        <p className="auth-notice">
          Signing up via an invite ({referralCode}) — you&apos;ll both get bonus credits once you
          verify your email.
        </p>
      )}
      {googleEnabled && (
        <a href={api.googleLoginUrl()} className="btn btn-ghost btn-sm">
          Continue with Google
        </a>
      )}
      {error && <p className="auth-error">{error}</p>}
      {notice && <p className="auth-notice">{notice}</p>}
    </form>
  );
}
