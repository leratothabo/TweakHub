/**
 * Thin client for the TweakHub API (apps/api). Every call reads the base
 * URL from NEXT_PUBLIC_API_URL so this works unchanged across dev/staging/
 * prod — see .env.example.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3001";

export type ToolCategory = "pdf" | "image" | "video" | "audio" | "document";

export interface ToolSummary {
  name: string;
  label: string;
  category: ToolCategory;
  base_credits: number;
  is_async: boolean;
}

export interface CreditPackage {
  credits: number;
  price_usd: number;
  price_zar: number;
}

export type PaymentMethod =
  | "card"
  | "mtn_momo"
  | "airtel_money"
  | "orange_money"
  | "mpesa"
  | "wave"
  | "bank_transfer";

export interface BankTransferDetails {
  payee_name: string;
  payee_description: string;
  bank_name: string;
  account_number: string;
}

/**
 * What POST /api/credits/purchase returns — the shape differs by
 * `payment_method`: "dpo" (every method except bank_transfer) redirects
 * the browser to `payment_url`; "bank_transfer" is a direct EFT with no
 * redirect at all, so it comes back with the reference + bank details to
 * show instead. See services/credit_service.py's initiate_purchase().
 */
export type PurchaseResult =
  | {
      payment_method: "dpo";
      payment_attempt_id: string;
      payment_url: string;
      credits: number;
      amount_usd: number;
    }
  | {
      payment_method: "bank_transfer";
      payment_attempt_id: string;
      bank_reference: string;
      bank_details: BankTransferDetails;
      credits: number;
      amount_usd: number;
    };

export type JobStatus = "pending" | "processing" | "succeeded" | "failed" | "expired";

/**
 * What both POST /api/tools/{tool}/process and GET /api/jobs/{id} return
 * — services/job_presenter.py builds the same shape for both, since
 * under the hood they're reading the same ProcessingJob row. Most tools
 * come back from processTool() already `succeeded` (resolved inline, in
 * that request); tools in the backend's ASYNC_TOOL_NAMES (video-category
 * tools, and anything routed through LibreOffice/Playwright/OCR) come
 * back `pending` with isAsync=true — pollJob() is how the caller finds
 * out when one of those finishes.
 */
export interface JobResult {
  jobId: string;
  toolName: string;
  status: JobStatus;
  isAsync: boolean;
  creditsSpent: number;
  creditBalance?: number;
  createdAt: string | null;
  finishedAt: string | null;
  downloadUrl?: string;
  contentType?: string;
  filename?: string;
  expiresAt?: string;
  meta?: Record<string, unknown>;
  error?: string;
}

function toJobResult(body: Record<string, unknown>): JobResult {
  return {
    jobId: body.job_id as string,
    toolName: body.tool_name as string,
    status: body.status as JobStatus,
    isAsync: Boolean(body.is_async),
    creditsSpent: Number(body.credits_spent ?? 0),
    creditBalance: body.credit_balance != null ? Number(body.credit_balance) : undefined,
    createdAt: (body.created_at as string) ?? null,
    finishedAt: (body.finished_at as string) ?? null,
    downloadUrl: body.download_url as string | undefined,
    contentType: body.content_type as string | undefined,
    filename: body.filename as string | undefined,
    expiresAt: body.expires_at as string | undefined,
    meta: (body.meta as Record<string, unknown>) ?? undefined,
    error: body.error as string | undefined,
  };
}

function authHeaders(token: string | null): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Thrown by handle() on any non-2xx response. Callers that need to branch
 * on *why* a request failed (e.g. AdminPage telling a 403 "not an admin"
 * apart from a network/500 error) should check `.status` rather than
 * pattern-matching on `.message`, which is just the server's human-
 * readable detail string and isn't a stable contract. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `Request failed: ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async listTools(category?: ToolCategory): Promise<{ count: number; tools: ToolSummary[] }> {
    const url = new URL(`${API_URL}/api/tools`);
    if (category) url.searchParams.set("category", category);
    return handle(await fetch(url.toString()));
  },

  /**
   * `extraFiles` is for tools that combine multiple inputs (pdf_merge,
   * video_merge, audio_merge, pdf_compare, subtitle_burn). `options` is a
   * JSON object of tool-specific parameters — see docs/engines.md for what
   * each tool reads (e.g. {angle: 180} for pdf_rotate, {password: "..."}
   * for pdf_protect, {target_format: "webp"} for image_convert).
   *
   * Returns as soon as the API responds — `succeeded` for most tools
   * (resolved inline server-side), or `pending`/isAsync=true for
   * ASYNC_TOOL_NAMES tools (video + LibreOffice/Playwright/OCR-backed
   * conversions). Callers should check `isAsync` and, if true, poll
   * pollJob() rather than treating the initial result as final.
   */
  async processTool(
    toolName: string,
    file: File,
    token: string,
    options: Record<string, unknown> = {},
    extraFiles: File[] = []
  ): Promise<JobResult> {
    const formData = new FormData();
    formData.append("file", file);
    for (const f of extraFiles) formData.append("extra_files", f);
    formData.append("options", JSON.stringify(options));

    const res = await fetch(`${API_URL}/api/tools/${toolName}/process`, {
      method: "POST",
      headers: authHeaders(token),
      body: formData,
    });

    if (!res.ok && res.status !== 202) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed: ${res.status}`);
    }

    return toJobResult(await res.json());
  },

  /** Current status of a job — poll this for a result whose isAsync was true. */
  async getJob(jobId: string, token: string): Promise<JobResult> {
    return toJobResult(await handle(await fetch(`${API_URL}/api/jobs/${jobId}`, { headers: authHeaders(token) })));
  },

  /**
   * Polls getJob() until it leaves pending/processing, or `timeoutMs`
   * elapses. Used for tools where processTool() came back isAsync=true.
   */
  async pollJob(
    jobId: string,
    token: string,
    { intervalMs = 2000, timeoutMs = 15 * 60 * 1000 }: { intervalMs?: number; timeoutMs?: number } = {}
  ): Promise<JobResult> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const job = await this.getJob(jobId, token);
      if (job.status !== "pending" && job.status !== "processing") return job;
      if (Date.now() > deadline) {
        throw new Error(`Timed out waiting for job ${jobId} (last status: ${job.status})`);
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  },

  async getCreditPackages(): Promise<{ packages: Record<string, CreditPackage> }> {
    return handle(await fetch(`${API_URL}/api/credits/packages`));
  },

  async getBalance(token: string): Promise<{ user_id: string; credit_balance: number }> {
    return handle(
      await fetch(`${API_URL}/api/credits/balance`, { headers: authHeaders(token) })
    );
  },

  async purchaseCredits(packageKey: string, method: PaymentMethod, token: string): Promise<PurchaseResult> {
    return handle(
      await fetch(`${API_URL}/api/credits/purchase`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders(token) },
        body: JSON.stringify({ package_key: packageKey, method }),
      })
    );
  },

  /** The bank-transfer payment-instructions PDF (routes/payments.py) as a
   * Blob. Unlike processTool()'s downloadUrl (a signed, tokenless URL —
   * services/storage_service.py), this route checks the bearer token
   * directly (it's re-fetchable any time, not a one-shot job result), so
   * a plain `<a href>`/window.open() can't carry the Authorization header
   * a browser navigation needs. Callers turn this into an object URL —
   * see BankTransferInstructions.tsx. */
  async getBankTransferInvoicePdf(attemptId: string, token: string): Promise<Blob> {
    const res = await fetch(`${API_URL}/api/payments/bank-transfer/${attemptId}/invoice`, {
      headers: authHeaders(token),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed: ${res.status}`);
    }
    return res.blob();
  },

  async signup(
    email: string,
    password: string,
    fullName?: string,
    /** Another user's referral code (see api.getReferral) — usually
     * picked up from a `?ref=` link, not typed in by hand. An unknown or
     * stale code is silently ignored server-side, not an error. */
    ref?: string
  ): Promise<{ user_id: string; email: string; is_email_verified: boolean; message: string }> {
    return handle(
      await fetch(`${API_URL}/api/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName, ref: ref || undefined }),
      })
    );
  },

  /** The signed-in user's own referral code + a ready-to-share link.
   * Bonus credits land on both sides once the invitee verifies their
   * email (not at signup) — see docs/TODO.md. */
  async getReferral(token: string): Promise<{
    referral_code: string;
    referral_link: string;
    bonus_credits_invitee: number;
    bonus_credits_referrer: number;
  }> {
    return handle(
      await fetch(`${API_URL}/api/auth/referral`, { headers: authHeaders(token) })
    );
  },

  async login(email: string, password: string): Promise<{ access_token: string; user_id: string }> {
    return handle(
      await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
    );
  },

  async verifyEmail(token: string): Promise<{ user_id: string; is_email_verified: boolean }> {
    return handle(
      await fetch(`${API_URL}/api/auth/verify-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      })
    );
  },

  async requestPasswordReset(email: string): Promise<{ message: string }> {
    return handle(
      await fetch(`${API_URL}/api/auth/request-password-reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      })
    );
  },

  async resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return handle(
      await fetch(`${API_URL}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      })
    );
  },

  /** Whether GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are configured on the
   * API — lets the UI decide whether to show a "Sign in with Google"
   * button at all, rather than showing one that 501s on click. */
  async getGoogleOAuthStatus(): Promise<{ enabled: boolean }> {
    return handle(await fetch(`${API_URL}/api/auth/google/status`));
  },

  /** Not fetched — this is a full-page navigation target. GET
   * /api/auth/google/login 302s straight to Google's consent screen;
   * Google then redirects the browser back to
   * /api/auth/google/callback, which redirects again to `${base_url}/
   * ?oauth_token=...` (success) or `?oauth_error=1` (failure) — see
   * page.tsx's handling of those query params. */
  googleLoginUrl(): string {
    return `${API_URL}/api/auth/google/login`;
  },

  // -- Team/business multi-seat accounts (routes/organizations.py) --------
  // v1: a user belongs to at most one organization — see
  // services/organization_service.py's docstring.

  /** Throws (404) when the signed-in user doesn't belong to an org yet —
   * OrganizationCard treats that as "show the create-org form". */
  async getMyOrganization(token: string): Promise<OrganizationInfo> {
    return handle(await fetch(`${API_URL}/api/organizations/me`, { headers: authHeaders(token) }));
  },

  async createOrganization(
    name: string,
    planTier: "business" | "enterprise",
    token: string
  ): Promise<{ id: string; name: string; plan_tier: string; credit_balance: number }> {
    return handle(
      await fetch(`${API_URL}/api/organizations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders(token) },
        body: JSON.stringify({ name, plan_tier: planTier }),
      })
    );
  },

  async inviteOrgMember(email: string, role: "admin" | "member", token: string): Promise<OrgMember> {
    return handle(
      await fetch(`${API_URL}/api/organizations/invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders(token) },
        body: JSON.stringify({ email, role }),
      })
    );
  },

  /** `inviteToken` comes from a team invite link (`?invite_token=...`,
   * mirroring the `?ref=` and `?oauth_token=` patterns — see
   * page.tsx). `token` is the *accepting user's own* signed-in session,
   * separate from the invite token itself. */
  async acceptOrgInvite(inviteToken: string, token: string): Promise<OrgMember> {
    return handle(
      await fetch(`${API_URL}/api/organizations/accept-invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders(token) },
        body: JSON.stringify({ token: inviteToken }),
      })
    );
  },

  async removeOrgMember(memberId: string, token: string): Promise<{ message: string }> {
    return handle(
      await fetch(`${API_URL}/api/organizations/members/${memberId}`, {
        method: "DELETE",
        headers: authHeaders(token),
      })
    );
  },

  // -- Admin: confirming direct bank-transfer payments (routes/admin.py) --
  // Gated by User.is_admin server-side — both calls 403 for anyone else.

  async listPendingBankTransfers(token: string): Promise<{ pending: PendingBankTransfer[] }> {
    return handle(
      await fetch(`${API_URL}/api/admin/bank-transfers/pending`, { headers: authHeaders(token) })
    );
  },

  async confirmBankTransfer(attemptId: string, token: string): Promise<{ status: string; credits_granted: boolean }> {
    return handle(
      await fetch(`${API_URL}/api/admin/bank-transfers/${attemptId}/confirm`, {
        method: "POST",
        headers: authHeaders(token),
      })
    );
  },
};

export interface PendingBankTransfer {
  id: string;
  user_email: string | null;
  package_key: string;
  amount_usd: number;
  credits: number;
  bank_reference: string;
  created_at: string | null;
}

export interface OrgMember {
  id: string;
  email: string;
  role: "owner" | "admin" | "member";
  status: "joined" | "invited";
  joined_at: string | null;
}

export interface OrganizationInfo {
  id: string;
  name: string;
  plan_tier: string;
  credit_balance: number;
  my_role: "owner" | "admin" | "member";
  members: OrgMember[];
}
