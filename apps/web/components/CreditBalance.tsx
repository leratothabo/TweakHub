"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Shows the signed-in user's credit balance. Pass the JWT from your auth flow. */
export default function CreditBalance({ token }: { token: string | null }) {
  const [balance, setBalance] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .getBalance(token)
      .then((res) => setBalance(res.credit_balance))
      .catch((err) => setError(err.message));
  }, [token]);

  if (!token) {
    return <div style={styles.pill}>Sign in to see your credits</div>;
  }

  if (error) {
    return <div style={{ ...styles.pill, color: "var(--danger)" }}>Couldn&apos;t load balance</div>;
  }

  return (
    <div style={styles.pill} className="tabular-nums">
      <span style={styles.dot} />
      {balance === null ? "…" : `${balance.toLocaleString()} credits`}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  pill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 14px",
    borderRadius: 999,
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    fontSize: 14,
    fontWeight: 600,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "var(--accent)",
  },
};
