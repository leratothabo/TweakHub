"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Logo from "@/components/Logo";
import { api } from "@/lib/api";

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get("token");
  // useSearchParams() resolves synchronously (unlike window.location, which
  // needs an effect), so the token-less case is derived as initial state
  // rather than set from inside the effect below.
  const [status, setStatus] = useState<"pending" | "ok" | "error">(token ? "pending" : "error");
  const [message, setMessage] = useState(token ? "Verifying…" : "Missing verification token.");

  useEffect(() => {
    if (!token) return;
    api
      .verifyEmail(token)
      .then(() => {
        setStatus("ok");
        setMessage("Your email is verified — you can sign in now.");
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Verification failed.");
      });
  }, [token]);

  return (
    <main className="container" style={{ paddingTop: 80, textAlign: "center" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
        <Logo />
      </div>
      <h1 style={{ fontSize: 22 }}>Email verification</h1>
      <p style={{ color: status === "error" ? "var(--danger)" : "var(--success)" }}>{message}</p>
      <Link href="/" style={{ color: "var(--accent-2)" }}>
        Back to TweakHub
      </Link>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
