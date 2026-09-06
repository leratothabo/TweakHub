"use client";

import { useEffect, useState } from "react";
import { api, Subscription } from "@/lib/api";

const STATUS_LABELS: Record<Subscription["status"], string> = {
  pending: "Pending first payment",
  active: "Active",
  past_due: "Payment failed — past due",
  cancelled: "Cancelled",
};

const PLAN_LABELS: Record<string, string> = { pro: "Pro", business: "Business" };

/** Minimal "you're subscribed" display + cancel button — not a full
 * billing dashboard (no upgrade/downgrade/proration UI; see
 * services/subscription_service.py's known limitations). Renders nothing
 * for a signed-out user or one with no subscription at all. */
export default function SubscriptionStatus({ token }: { token: string | null }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setSubscription(null);
      setLoaded(false);
      return;
    }
    api
      .getMySubscription(token)
      .then(setSubscription)
      .catch(() => setSubscription(null))
      .finally(() => setLoaded(true));
  }, [token]);

  async function cancel() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setSubscription(await api.cancelSubscription(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel subscription");
    } finally {
      setBusy(false);
    }
  }

  if (!token || !loaded || !subscription || subscription.status === "cancelled") return null;

  const renewsOrEnds = subscription.current_period_end
    ? new Date(subscription.current_period_end).toLocaleDateString()
    : null;

  return (
    <div style={styles.card}>
      <div>
        <strong>{PLAN_LABELS[subscription.plan_key] ?? subscription.plan_key} plan</strong>
        {" — "}
        {STATUS_LABELS[subscription.status]}
        {renewsOrEnds && !subscription.cancel_at_period_end && ` · renews ${renewsOrEnds}`}
        {renewsOrEnds && subscription.cancel_at_period_end && ` · ends ${renewsOrEnds}`}
      </div>
      {!subscription.cancel_at_period_end && (
        <button disabled={busy} onClick={cancel} style={styles.cancelButton}>
          {busy ? "Cancelling…" : "Cancel subscription"}
        </button>
      )}
      {subscription.cancel_at_period_end && <span style={styles.cancelling}>Cancelling</span>}
      {error && <p style={{ color: "var(--danger)", fontSize: 13, width: "100%", margin: "8px 0 0" }}>{error}</p>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 12,
    padding: "12px 16px",
    borderRadius: "var(--radius)",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    fontSize: 14,
    marginBottom: 16,
  },
  cancelButton: {
    marginLeft: "auto",
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text-muted)",
    fontSize: 13,
  },
  cancelling: {
    marginLeft: "auto",
    fontSize: 13,
    color: "var(--text-muted)",
  },
};
