"use client";

import { useEffect, useState } from "react";
import { api, CreditPackage, PaymentMethod, PurchaseResult } from "@/lib/api";
import BankTransferInstructions from "./BankTransferInstructions";
import PaymentMethodSelector from "./PaymentMethodSelector";

interface Props {
  token: string | null;
  currency?: "usd" | "zar";
}

const PACKAGE_ORDER = ["starter", "popular", "pro", "business"];

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

  const entries = Object.entries(packages).sort(
    (a, b) => PACKAGE_ORDER.indexOf(a[0]) - PACKAGE_ORDER.indexOf(b[0])
  );

  return (
    <div>
      <div className="pricing-grid">
        {entries.map(([key, pkg]) => {
          const isPopular = key === "popular";
          const active = selected === key;
          return (
            <button
              key={key}
              onClick={() => setSelected(key)}
              className={`card card-hover pricing-card${isPopular ? " pricing-card-popular" : ""}`}
              style={{ borderColor: active ? "var(--accent-2)" : undefined }}
            >
              {isPopular && <span className="pricing-badge">Most popular</span>}
              <div className="pricing-label">{key}</div>
              <div className="pricing-price tabular-nums">
                {currency === "usd" ? `$${pkg.price_usd}` : `R${pkg.price_zar}`}
              </div>
              <div className="pricing-credits tabular-nums">{pkg.credits.toLocaleString()} credits</div>
            </button>
          );
        })}
      </div>

      {selected && (
        <div style={{ marginTop: 24 }}>
          <PaymentMethodSelector value={method} onChange={setMethod} />
          <button disabled={!token || busy} onClick={buy} className="btn btn-primary">
            {busy
              ? method === "bank_transfer"
                ? "Preparing…"
                : "Redirecting…"
              : token
                ? "Buy credits"
                : "Sign in to buy"}
          </button>
          {error && <p style={{ color: "var(--danger)", marginTop: 10 }}>{error}</p>}
          {bankTransferResult && token && (
            <BankTransferInstructions result={bankTransferResult} token={token} />
          )}
        </div>
      )}
    </div>
  );
}
