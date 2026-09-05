"use client";

import { useEffect, useState } from "react";
import { api, CreditPackage, PaymentMethod, PurchaseResult } from "@/lib/api";
import BankTransferInstructions from "./BankTransferInstructions";
import PaymentMethodSelector from "./PaymentMethodSelector";

interface Props {
  token: string | null;
  currency?: "usd" | "zar";
}

/** Credit package picker + purchase flow. Every method except bank_transfer
 * redirects to DPO's hosted payment page; bank_transfer has no gateway to
 * redirect to, so it renders BankTransferInstructions in place instead —
 * see purchaseCredits()'s PurchaseResult union. */
export default function CreditPackages({ token, currency = "usd" }: Props) {
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
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
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
