"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Shows the signed-in user's own referral link and lets them copy it.
 * Bonus credits land on both sides once the invitee verifies their email
 * (not at signup) — see docs/TODO.md. */
export default function ReferralCard({ token }: { token: string | null }) {
  const [info, setInfo] = useState<{
    referral_link: string;
    bonus_credits_invitee: number;
    bonus_credits_referrer: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!token) {
      // Clears out a stale referral_link from a previous token so a
      // token flip (e.g. logout then a different login) can't briefly
      // render the old account's info while the new fetch is in flight.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInfo(null);
      return;
    }
    api
      .getReferral(token)
      .then(setInfo)
      .catch((err) => setError(err.message));
  }, [token]);

  if (!token || error || !info) return null;

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(info!.referral_link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied by the browser — the link is still
      // shown in the input below for a manual copy either way.
    }
  }

  return (
    <div style={styles.card}>
      <p style={styles.title}>
        Invite a friend — you get {info.bonus_credits_referrer} credits, they get{" "}
        {info.bonus_credits_invitee}, once they verify their email.
      </p>
      <div style={styles.row}>
        <input readOnly value={info.referral_link} style={styles.input} onFocus={(e) => e.target.select()} />
        <button onClick={copyLink} style={styles.button}>
          {copied ? "Copied!" : "Copy link"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: 16,
    borderRadius: "var(--radius)",
    background: "var(--surface)",
    border: "1px solid var(--border)",
  },
  title: { margin: "0 0 12px", fontSize: 14 },
  row: { display: "flex", gap: 8, flexWrap: "wrap" },
  input: {
    flex: 1,
    minWidth: 220,
    padding: "8px 12px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    color: "var(--text)",
    fontSize: 13,
  },
  button: {
    padding: "8px 16px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent-2)",
    color: "#12151c",
    fontWeight: 700,
  },
};
