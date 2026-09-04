"use client";

import { useEffect, useState } from "react";
import AuthPanel from "@/components/AuthPanel";
import Logo from "@/components/Logo";
import { api, ApiError, PendingBankTransfer } from "@/lib/api";

/**
 * Internal admin surface — today, exactly one job: confirming a direct
 * bank-transfer payment once its deposit has actually landed in
 * TweakHub's account (routes/admin.py; there's no webhook for a plain
 * EFT the way there is for DPO's routes/payments.py callback).
 *
 * Not linked from anywhere in the main app on purpose — reachable only by
 * URL, gated server-side by User.is_admin (there's no self-service way to
 * grant that flag; set it directly in the database). Reuses AuthPanel for
 * sign-in rather than assuming a token from the main page's React state,
 * since this is a separate page load with none of that in-memory state.
 */
export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingBankTransfer[] | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  async function loadPending(authToken: string) {
    setError(null);
    setForbidden(false);
    try {
      const res = await api.listPendingBankTransfers(authToken);
      setPending(res.pending);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError(err instanceof Error ? err.message : "Could not load pending transfers.");
      }
    }
  }

  useEffect(() => {
    // Fetches (and sets state from) the pending list whenever a token
    // becomes available — a sign-in, not a re-render loop, since `token`
    // only changes on sign-in/out. Same "fetch on dependency change"
    // shape as ToolRouter.tsx's effects.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (token) loadPending(token);
  }, [token]);

  async function confirm(id: string) {
    if (!token) return;
    setConfirmingId(id);
    setError(null);
    try {
      await api.confirmBankTransfer(id, token);
      await loadPending(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm this transfer.");
    } finally {
      setConfirmingId(null);
    }
  }

  return (
    <main className="container" style={{ paddingTop: 60, paddingBottom: 80 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 32 }}>
        <Logo size={36} />
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>Admin</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 13 }}>
            Bank-transfer confirmations
          </p>
        </div>
      </div>

      {!token && (
        <div style={{ maxWidth: 360 }}>
          <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 16 }}>
            Sign in with an admin account to review pending bank transfers.
          </p>
          <AuthPanel onAuthenticated={setToken} />
        </div>
      )}

      {token && forbidden && (
        <p style={{ color: "var(--danger)" }}>
          This account doesn&apos;t have admin access. Ask whoever manages TweakHub&apos;s database to set
          your user&apos;s is_admin flag.
        </p>
      )}

      {token && !forbidden && (
        <>
          {error && <p style={{ color: "var(--danger)", marginBottom: 16 }}>{error}</p>}
          {pending === null ? (
            <p style={{ color: "var(--text-muted)" }}>Loading…</p>
          ) : pending.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>No pending bank transfers.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Reference</th>
                    <th style={styles.th}>Customer</th>
                    <th style={styles.th}>Package</th>
                    <th style={styles.th}>Amount</th>
                    <th style={styles.th}>Requested</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((row) => (
                    <tr key={row.id}>
                      <td style={{ ...styles.td, fontWeight: 700 }}>{row.bank_reference}</td>
                      <td style={styles.td}>{row.user_email ?? "—"}</td>
                      <td style={styles.td}>
                        {row.package_key} ({row.credits.toLocaleString()} credits)
                      </td>
                      <td style={styles.td}>{row.amount_usd.toFixed(2)} USD</td>
                      <td style={styles.td}>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                      <td style={styles.td}>
                        <button
                          onClick={() => confirm(row.id)}
                          disabled={confirmingId === row.id}
                          style={styles.confirmButton}
                        >
                          {confirmingId === row.id ? "Confirming…" : "Mark received"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  table: { width: "100%", borderCollapse: "collapse", fontSize: 14 },
  th: {
    textAlign: "left",
    padding: "8px 12px",
    borderBottom: "1px solid var(--border)",
    color: "var(--text-muted)",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  td: { padding: "10px 12px", borderBottom: "1px solid var(--border)" },
  confirmButton: {
    padding: "6px 14px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent)",
    color: "#12151c",
    fontWeight: 700,
    fontSize: 13,
  },
};
