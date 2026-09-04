"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Logo from "@/components/Logo";
import { api } from "@/lib/api";

function RequestResetForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const res = await api.requestPasswordReset(email);
    setMessage(res.message);
  }

  return (
    <form onSubmit={submit} style={{ display: "flex", gap: 8, justifyContent: "center" }}>
      <input
        type="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        style={{
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
        }}
      />
      <button
        type="submit"
        style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "var(--accent-2)", color: "#12151c", fontWeight: 700 }}
      >
        Send reset link
      </button>
      {message && <p style={{ width: "100%", color: "var(--success)" }}>{message}</p>}
    </form>
  );
}

function ConfirmResetForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.resetPassword(token, password);
      setStatus(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "flex", gap: 8, justifyContent: "center" }}>
      <input
        type="password"
        placeholder="New password"
        minLength={8}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        style={{
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
        }}
      />
      <button
        type="submit"
        style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "var(--accent)", color: "#12151c", fontWeight: 700 }}
      >
        Reset password
      </button>
      {status && <p style={{ width: "100%", color: "var(--success)" }}>{status}</p>}
      {error && <p style={{ width: "100%", color: "var(--danger)" }}>{error}</p>}
    </form>
  );
}

function ResetPasswordInner() {
  const params = useSearchParams();
  const token = params.get("token");

  return (
    <main className="container" style={{ paddingTop: 80, textAlign: "center" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
        <Logo />
      </div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>Reset your password</h1>
      {token ? <ConfirmResetForm token={token} /> : <RequestResetForm />}
      <p style={{ marginTop: 24 }}>
        <Link href="/" style={{ color: "var(--accent-2)" }}>
          Back to TweakHub
        </Link>
      </p>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordInner />
    </Suspense>
  );
}
