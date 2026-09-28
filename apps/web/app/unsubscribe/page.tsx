"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Logo from "@/components/Logo";
import { api } from "@/lib/api";

function UnsubscribeInner() {
  const params = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"pending" | "ok" | "error">(token ? "pending" : "error");
  const [message, setMessage] = useState(token ? "Unsubscribing…" : "Missing unsubscribe token.");

  useEffect(() => {
    if (!token) return;
    api
      .unsubscribe(token)
      .then((res) => {
        setStatus("ok");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Something went wrong.");
      });
  }, [token]);

  return (
    <main className="container" style={{ paddingTop: 80, textAlign: "center" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
        <Logo />
      </div>
      <h1 style={{ fontSize: 22 }}>Unsubscribe</h1>
      <p style={{ color: status === "error" ? "var(--danger)" : "var(--success)" }}>{message}</p>
      <Link href="/" style={{ color: "var(--accent-2)" }}>
        Back to TweakHub
      </Link>
    </main>
  );
}

export default function UnsubscribePage() {
  return (
    <Suspense fallback={null}>
      <UnsubscribeInner />
    </Suspense>
  );
}
