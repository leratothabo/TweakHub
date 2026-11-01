"use client";

import { useEffect, useState } from "react";
import AuthPanel from "@/components/AuthPanel";
import Logo from "@/components/Logo";
import { api, ApiError, PendingBankTransfer, StatementPreview, StatementMatchStatus } from "@/lib/api";

const STATUS_LABELS: Record<StatementMatchStatus, { label: string; color: string }> = {
  match: { label: "Match", color: "var(--accent)" },
  underpaid: { label: "Underpaid", color: "var(--danger)" },
  unknown_reference: { label: "Unknown reference", color: "var(--danger)" },
  not_pending: { label: "Cancelled / failed", color: "var(--text-muted)" },
  already_confirmed: { label: "Already confirmed", color: "var(--text-muted)" },
};

function rand(value: number | null): string {
  return value === null ? "—" : `R${value.toFixed(2)}`;
}

/**
 * Internal admin surface — confirming direct bank-transfer payments,
 * either by uploading a bank-statement CSV (matched by TweakHub reference,
 * reviewed, then batch-confirmed) or one at a time once a deposit has
 * actually landed in
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
  const [statementFile, setStatementFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statementBusy, setStatementBusy] = useState(false);
  const [statementMessage, setStatementMessage] = useState<string | null>(null);

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

  async function checkStatement() {
    if (!token || !statementFile) return;
    setStatementBusy(true);
    setError(null);
    setStatementMessage(null);
    try {
      const result = await api.previewBankStatement(statementFile, token);
      setPreview(result);
      // Only clean matches are pre-ticked; anything flagged needs a human
      // decision (and a manual "Mark received" if it's actually fine).
      setSelected(
        new Set(result.rows.filter((r) => r.status === "match" && r.attempt_id).map((r) => r.attempt_id as string))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read this statement.");
    } finally {
      setStatementBusy(false);
    }
  }

  async function confirmSelected() {
    if (!token || selected.size === 0) return;
    setStatementBusy(true);
    setError(null);
    try {
      const res = await api.confirmStatementMatches(Array.from(selected), token);
      setStatementMessage(
        `Confirmed ${res.confirmed.length} payment${res.confirmed.length === 1 ? "" : "s"}` +
          (res.skipped.length ? `, skipped ${res.skipped.length}.` : ".")
      );
      setPreview(null);
      setSelected(new Set());
      setStatementFile(null);
      await loadPending(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm these payments.");
    } finally {
      setStatementBusy(false);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
          <section style={styles.card}>
            <h2 style={{ margin: "0 0 6px", fontSize: 17 }}>Match a bank statement</h2>
            <p style={{ margin: "0 0 14px", color: "var(--text-muted)", fontSize: 13 }}>
              Download your statement as CSV from online banking and upload it here. Lines with a
              TweakHub reference are matched to pending payments. Nothing is credited until you
              confirm.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="file"
                accept=".csv,text/csv,.txt"
                onChange={(e) => {
                  setStatementFile(e.target.files?.[0] ?? null);
                  setPreview(null);
                  setStatementMessage(null);
                }}
              />
              <button
                onClick={checkStatement}
                disabled={!statementFile || statementBusy}
                style={styles.confirmButton}
              >
                {statementBusy && !preview ? "Checking…" : "Check statement"}
              </button>
            </div>

            {statementMessage && <p style={{ margin: "14px 0 0", color: "var(--accent)" }}>{statementMessage}</p>}

            {preview && (
              <div style={{ marginTop: 18 }}>
                <p style={{ margin: "0 0 10px", fontSize: 13, color: "var(--text-muted)" }}>
                  {preview.summary.lines_with_reference} statement line
                  {preview.summary.lines_with_reference === 1 ? "" : "s"} with a TweakHub reference ·{" "}
                  {preview.summary.matches} ready to confirm · {preview.summary.needs_review} need review
                </p>
                {preview.rows.length === 0 ? (
                  <p style={{ color: "var(--text-muted)" }}>No TweakHub references found in this file.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={styles.table}>
                      <thead>
                        <tr>
                          <th style={styles.th}></th>
                          <th style={styles.th}>Reference</th>
                          <th style={styles.th}>Status</th>
                          <th style={styles.th}>Paid</th>
                          <th style={styles.th}>Expected</th>
                          <th style={styles.th}>Customer</th>
                          <th style={styles.th}>Statement line</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row) => {
                          const selectable =
                            !!row.attempt_id && (row.status === "match" || row.status === "underpaid");
                          return (
                            <tr key={row.reference}>
                              <td style={styles.td}>
                                {selectable && (
                                  <input
                                    type="checkbox"
                                    aria-label={`Confirm ${row.reference}`}
                                    checked={selected.has(row.attempt_id as string)}
                                    onChange={() => toggle(row.attempt_id as string)}
                                  />
                                )}
                              </td>
                              <td style={{ ...styles.td, fontWeight: 700 }}>{row.reference}</td>
                              <td style={{ ...styles.td, color: STATUS_LABELS[row.status].color, fontWeight: 600 }}>
                                {STATUS_LABELS[row.status].label}
                              </td>
                              <td style={styles.td}>{rand(row.paid_zar)}</td>
                              <td style={styles.td}>{rand(row.expected_zar)}</td>
                              <td style={styles.td}>{row.user_email ?? "—"}</td>
                              <td style={{ ...styles.td, color: "var(--text-muted)", fontSize: 12 }}>
                                {row.statement_lines.join(" | ")}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                <button
                  onClick={confirmSelected}
                  disabled={selected.size === 0 || statementBusy}
                  style={{ ...styles.confirmButton, marginTop: 14 }}
                >
                  {statementBusy ? "Confirming…" : `Confirm ${selected.size} selected`}
                </button>
              </div>
            )}
          </section>

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
  card: {
    border: "1px solid var(--border)",
    borderRadius: 12,
    padding: 18,
    marginBottom: 28,
  },
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
