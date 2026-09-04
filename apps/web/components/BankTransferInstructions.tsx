"use client";

import { useState } from "react";
import { api, PurchaseResult } from "@/lib/api";

interface Props {
  result: Extract<PurchaseResult, { payment_method: "bank_transfer" }>;
  token: string;
}

/** Shown in place of CreditPackages' usual "redirecting to DPO" flow when
 * the customer picked Bank Transfer — a direct EFT has no gateway to
 * redirect to, so this renders TweakHub's own account details plus the
 * reference to use, and offers the same details as a downloadable PDF
 * (routes/payments.py's invoice endpoint). Credits land once TweakHub
 * confirms the deposit (routes/admin.py) — there's no "waiting for
 * webhook" spinner here because there is no webhook. */
export default function BankTransferInstructions({ result, token }: Props) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  async function downloadInvoice() {
    setDownloadError(null);
    setDownloading(true);
    try {
      const blob = await api.getBankTransferInvoicePdf(result.payment_attempt_id, token);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${result.bank_reference}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Give the browser a moment to pick up the download before revoking.
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Could not download the invoice.");
    } finally {
      setDownloading(false);
    }
  }

  const { bank_details } = result;

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <h3 style={styles.title}>Bank transfer instructions</h3>
        <span style={styles.pill}>Awaiting payment</span>
      </div>

      <dl style={styles.grid}>
        <dt style={styles.dt}>Pay to</dt>
        <dd style={styles.dd}>
          {bank_details.payee_name} ({bank_details.payee_description})
        </dd>

        <dt style={styles.dt}>Bank</dt>
        <dd style={styles.dd}>{bank_details.bank_name}</dd>

        <dt style={styles.dt}>Account number</dt>
        <dd style={styles.dd}>{bank_details.account_number}</dd>

        <dt style={styles.dt}>Amount</dt>
        <dd style={styles.dd}>{result.amount_usd.toFixed(2)} USD</dd>

        <dt style={styles.dt}>Reference</dt>
        <dd style={{ ...styles.dd, ...styles.reference }}>{result.bank_reference}</dd>
      </dl>

      <p style={styles.notice}>
        Use the reference above on your transfer so we can match your payment. Your{" "}
        {result.credits.toLocaleString()} credits are added once we confirm the deposit — usually within
        one business day.
      </p>

      <button onClick={downloadInvoice} disabled={downloading} style={styles.downloadButton}>
        {downloading ? "Preparing…" : "Download as PDF"}
      </button>
      {downloadError && <p style={{ color: "var(--danger)", fontSize: 13 }}>{downloadError}</p>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    marginTop: 20,
    padding: 20,
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
  },
  headerRow: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 },
  title: { margin: 0, fontSize: 16 },
  pill: {
    fontSize: 11,
    fontWeight: 700,
    padding: "3px 10px",
    borderRadius: 999,
    background: "var(--surface-2)",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "140px 1fr",
    rowGap: 8,
    columnGap: 12,
    margin: "16px 0",
    fontSize: 14,
  },
  dt: { color: "var(--text-muted)" },
  dd: { margin: 0 },
  reference: { fontWeight: 800, color: "var(--accent)", letterSpacing: 0.5 },
  notice: { fontSize: 13, color: "var(--text-muted)", marginBottom: 16 },
  downloadButton: {
    padding: "10px 20px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text)",
    fontWeight: 700,
  },
};
