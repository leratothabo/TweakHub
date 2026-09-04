/**
 * VESTIGIAL as a client (see avx-client's note — ConvertAgent was never
 * confirmed as a real project either). The pairs below are still accurate
 * as documentation, though: apps/api/services/engines/document_convert.py
 * really does support all four via LibreOffice headless (pdf<->docx) and
 * Playwright+Chromium (html/markdown -> pdf). All four are also exactly
 * the kind of tool that goes through the real background-job-queue now
 * rather than resolving inline — see routes/tools.py's ASYNC_TOOL_NAMES
 * (every tool the `document` engine handles) and avx-client's note for
 * where the real job/polling system lives. If a tool ever needs to chain
 * conversions (e.g. markdown -> pdf -> watermark), that orchestration
 * belongs in apps/api/services, calling multiple engines in sequence.
 */
export interface ConvertAgentPair {
  from: string;
  to: string;
}

export const SUPPORTED_PAIRS: ConvertAgentPair[] = [
  { from: "pdf", to: "docx" },
  { from: "docx", to: "pdf" },
  { from: "html", to: "pdf" },
  { from: "markdown", to: "pdf" },
];
