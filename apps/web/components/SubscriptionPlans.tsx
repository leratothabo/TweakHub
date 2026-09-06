"use client";

import { useEffect, useState } from "react";
import { api, SubscriptionPlan } from "@/lib/api";

interface Props {
  token: string | null;
  /** Called after a successful subscribe redirect is kicked off, or after
   * cancel — lets a parent (e.g. SubscriptionStatus) know it might want
   * to re-fetch. Optional; CreditPackages doesn't currently use it. */
  onChanged?: () => void;
}

const PLAN_LABELS: Record<string, string> = { pro: "Pro", business: "Business" };

/** Recurring monthly subscription plans, billed via Paystack — separate
 * from CreditPackages' one-time DPO purchase flow above/alongside it.
 * Subscribing redirects to Paystack's hosted checkout, same
 * window.location.href pattern CreditPackages.buy() uses for DPO. */
export default function SubscriptionPlans({ token, onChanged }: Props) {
  const [plans, setPlans] = useState<Record<string, SubscriptionPlan>>({});
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSubscriptionPlans().then((res) => setPlans(res.plans));
  }, []);

  async function subscribe(planKey: string) {
    if (!token) return;
    setBusyPlan(planKey);
    setError(null);
    try {
      const result = await api.subscribe(planKey, token);
      onChanged?.();
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Subscription failed");
      setBusyPlan(null);
    }
  }

  return (
    <div>
      <div style={styles.grid}>
        {Object.entries(plans).map(([key, plan]) => (
          <div key={key} style={styles.card}>
            <div style={styles.planName}>{PLAN_LABELS[key] ?? key}</div>
            <div style={styles.price}>
              ${plan.price_usd}
              <span style={styles.perMonth}>/mo</span>
            </div>
            <div style={styles.credits}>{plan.monthly_credits.toLocaleString()} credits / month</div>
            <button
              disabled={!token || busyPlan !== null}
              onClick={() => subscribe(key)}
              style={styles.subscribeButton}
            >
              {busyPlan === key ? "Redirecting…" : token ? "Subscribe" : "Sign in to subscribe"}
            </button>
          </div>
        ))}
      </div>
      {error && <p style={{ color: "var(--danger)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: 12,
  },
  card: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: 20,
    textAlign: "left",
    color: "var(--text)",
  },
  planName: { fontSize: 14, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 },
  price: { fontSize: 28, fontWeight: 800, marginTop: 6, color: "var(--accent)" },
  perMonth: { fontSize: 14, fontWeight: 600, color: "var(--text-muted)" },
  credits: { fontSize: 13, color: "var(--text-muted)", marginTop: 4 },
  subscribeButton: {
    marginTop: 16,
    width: "100%",
    padding: "10px 20px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent)",
    color: "#12151c",
    fontWeight: 700,
  },
};
