"use client";

import { useEffect, useState } from "react";
import { api, OrganizationInfo } from "@/lib/api";

interface Props {
  token: string;
  /** Picked up from a `?invite_token=` link (see page.tsx) — accepted
   * automatically once we know the user is signed in. */
  pendingInviteToken: string | null;
  onInviteHandled: () => void;
}

/** Team/business multi-seat accounts — first cut. Shows a create-org form
 * for a user with no org, or the org's member list + an invite form for
 * one who has (or has joined) one. v1: a user belongs to at most one
 * organization — see services/organization_service.py. */
export default function OrganizationCard({ token, pendingInviteToken, onInviteHandled }: Props) {
  const [org, setOrg] = useState<OrganizationInfo | null | undefined>(undefined); // undefined = loading
  const [orgName, setOrgName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function refresh() {
    api
      .getMyOrganization(token)
      .then(setOrg)
      .catch(() => setOrg(null)); // 404 — no org yet
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!pendingInviteToken) return;
    api
      .acceptOrgInvite(pendingInviteToken, token)
      .then(() => {
        setNotice("You've joined the team.");
        refresh();
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't accept that invite"))
      .finally(() => onInviteHandled());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingInviteToken, token]);

  async function createOrg(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createOrganization(orgName, "business", token);
      setOrgName("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.inviteOrgMember(inviteEmail, "member", token);
      setNotice(`Invited ${inviteEmail}.`);
      setInviteEmail("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(memberId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.removeOrgMember(memberId, token);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (org === undefined) return null; // still loading — avoid a flash of the create-org form

  const canManage = org?.my_role === "owner" || org?.my_role === "admin";

  return (
    <div style={styles.card}>
      {org === null ? (
        <form onSubmit={createOrg} style={styles.row}>
          <p style={{ ...styles.title, width: "100%" }}>
            Business and enterprise plans can pool credits across a team. Create an organization to
            get started.
          </p>
          <input
            placeholder="Organization name"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            required
            style={styles.input}
          />
          <button type="submit" disabled={busy} style={styles.primaryButton}>
            {busy ? "…" : "Create organization"}
          </button>
        </form>
      ) : (
        <>
          <p style={styles.title}>
            {org.name} · {org.plan_tier} plan · {org.credit_balance} shared credits
          </p>
          <ul style={styles.memberList}>
            {org.members.map((m) => (
              <li key={m.id} style={styles.memberRow}>
                <span>
                  {m.email} — {m.role}
                  {m.status === "invited" && " (invited)"}
                </span>
                {canManage && m.role !== "owner" && (
                  <button onClick={() => removeMember(m.id)} disabled={busy} style={styles.linkButton}>
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
          {canManage && (
            <form onSubmit={invite} style={styles.row}>
              <input
                type="email"
                placeholder="teammate@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                style={styles.input}
              />
              <button type="submit" disabled={busy} style={styles.primaryButton}>
                {busy ? "…" : "Invite"}
              </button>
            </form>
          )}
        </>
      )}
      {error && <p style={styles.error}>{error}</p>}
      {notice && <p style={styles.notice}>{notice}</p>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: 16,
    borderRadius: "var(--radius)",
    background: "var(--surface)",
    border: "1px solid var(--border)",
  },
  title: { margin: "0 0 12px", fontSize: 14 },
  row: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 },
  memberList: { listStyle: "none", margin: "0 0 12px", padding: 0, display: "flex", flexDirection: "column", gap: 6 },
  memberRow: { display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, gap: 8 },
  input: {
    flex: 1,
    minWidth: 200,
    padding: "8px 12px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    color: "var(--text)",
    fontSize: 13,
  },
  primaryButton: {
    padding: "8px 16px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent-2)",
    color: "#12151c",
    fontWeight: 700,
  },
  linkButton: {
    background: "none",
    border: "none",
    color: "var(--danger)",
    fontSize: 12,
    textDecoration: "underline",
    cursor: "pointer",
  },
  error: { color: "var(--danger)", fontSize: 13, margin: "8px 0 0" },
  notice: { color: "var(--success)", fontSize: 13, margin: "8px 0 0" },
};
