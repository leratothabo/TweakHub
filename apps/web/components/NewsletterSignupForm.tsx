"use client";

import { useState } from "react";
import { api } from "@/lib/api";

/** Small email+consent form for the site footer -- the only place
 * POST /api/subscribers/newsletter-signup is reachable from today, since
 * there's no admin UI yet to send a campaign from. Consent checkbox is
 * unchecked by default and required (the API 400s without it). */
export default function NewsletterSignupForm() {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!consent) {
      setIsError(true);
      setMessage("Please check the consent box to subscribe.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.newsletterSignup(email, consent);
      setIsError(false);
      setMessage(res.message);
      setEmail("");
      setConsent(false);
    } catch (err) {
      setIsError(true);
      setMessage(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="newsletter-form" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
            fontSize: 13,
            width: 180,
          }}
        />
        <button
          type="submit"
          disabled={busy}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: "none",
            background: "var(--accent-2)",
            color: "#12151c",
            fontWeight: 700,
            fontSize: 13,
          }}
        >
          {busy ? "…" : "Subscribe"}
        </button>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-muted)" }}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        Email me product news and offers
      </label>
      {message && (
        <p style={{ margin: 0, fontSize: 12, color: isError ? "var(--danger)" : "var(--success)" }}>{message}</p>
      )}
    </form>
  );
}
