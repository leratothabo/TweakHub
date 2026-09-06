"use client";

import { useEffect, useState } from "react";
import { api, CreditPackage, PaymentMethod, PurchaseResult } from "@/lib/api";
import BankTransferInstructions from "./BankTransferInstructions";
import PaymentMethodSelector from "./PaymentMethodSelector";
import SubscriptionPlans from "./SubscriptionPlans";

interface Props {
  token: string | null;
  currency?: "usd" | "zar";
}

type Tab = "one-time" | "subscription";

/** Credit package picker + purchase flow, plus a tab over to the
 * recurring-subscription plans (SubscriptionPlans.tsx) — these are two
 * unrelated payment flows (DPO one-time top-ups vs. a Paystack-billed
 * monthly plan) that both belong under the same "get credits" heading, so
 * a tab keeps them from competing for the same section of the page
 * without merging their very different purchase flows into one
 * component. Every method except bank_transfer redirects to DPO's hosted
 * payment page; bank_transfer has no gateway to redirect to, so it
 * renders BankTransferInstructions in place instead — see
 * purchaseCredits()'s PurchaseResult union. */
export default function CreditPackages({ token, currency = "usd" }: Props) {
  const [tab, setTab] = useState<Tab>("one-time");
  const [packages, setPackages] = useState<Record<string, CreditPackage>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("card");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bankTransferResult, setBankTransferResult] = useState<
    Extract<PurchaseResult, { payment_method: "bank_transfer" }> | null
  >(null);

  useEffect(() => {
    api.getCreditPackages().then((res) => setPackages(res.packages));
  }, []);

  async function buy() {
    if (!token || !selected) return;
    setBusy(true);
    setError(null);
    setBankTransferResult(null);
    try {
      const result = await api.purchaseCredits(selected, method, token);
      if (result.payment_method === "bank_transfer") {
        setBankTransferResult(result);
      } else {
        window.location.href = result.payment_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Purchase failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={styles.tabRow}>
        <button
          onClick={() => setTab("one-time")}
          style={{ ...styles.tabButton, ...(tab === "one-time" ? styles.tabButtonActive : {}) }}
        >
          One-time credits
        </button>
        <button
          onClick={() => setTab("subscription")}
          style={{ ...styles.tabButton, ...(tab === "subscription" ? styles.tabButtonActive : {}) }}
        >
          Monthly subscription
        </button>
      </div>

      {tab === "subscription" ? (
        <SubscriptionPlans token={token} />
      ) : (
        <>
          <div style={styles.grid}>
            {Object.entries(packages).map(([key, pkg]) => (
              <button
                key={key}
                onClick={() => setSelected(key)}
                style={{
                  ...styles.card,
                  borderColor: selected === key ? "var(--accent)" : "var(--border)",
                }}
              >
                <div style={styles.credits}>{pkg.credits.toLocaleString()} credits</div>
                <div style={styles.price}>
                  {currency === "usd" ? `$${pkg.price_usd}` : `R${pkg.price_zar}`}
                </div>
                <div style={styles.label}>{key}</div>
              </button>
            ))}
          </div>

          {selected && (
            <div style={{ marginTop: 20 }}>
              <PaymentMethodSelector value={method} onChange={setMethod} />
              <button disabled={!token || busy} onClick={buy} style={styles.buyButton}>
                {busy
                  ? method === "bank_transfer"
                    ? "Preparing…"
                    : "Redirecting…"
                  : token
                    ? "Buy credits"
                    : "Sign in to buy"}
              </button>
              {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
              {bankTransferResult && token && (
                <BankTransferInstructions result={bankTransferResult} token={token} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  tabRow: {
    display: "flex",
    gap: 8,
    marginBottom: 16,
  },
  tabButton: {
    padding: "8px 16px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text-muted)",
    fontSize: 13,
    fontWeight: 600,
  },
  tabButtonActive: {
    background: "var(--surface-2)",
    borderColor: "var(--accent)",
    color: "var(--text)",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: 12,
  },
  card: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: 16,
    textAlign: "left",
    color: "var(--text)",
  },
  credits: { fontSize: 18, fontWeight: 700 },
  price: { fontSize: 24, fontWeight: 800, marginTop: 4, color: "var(--accent)" },
  label: { fontSize: 12, color: "var(--text-muted)", textTransform: "capitalize", marginTop: 6 },
  buyButton: {
    marginTop: 12,
    padding: "10px 20px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent)",
    color: "#12151c",
    fontWeight: 700,
  },
};
