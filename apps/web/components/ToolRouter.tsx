"use client";

import { useEffect, useState } from "react";
import { api, JobResult, ToolCategory, ToolSummary } from "@/lib/api";

const CATEGORIES: ToolCategory[] = ["pdf", "image", "video", "audio", "document"];

// Tools that combine multiple inputs — shows the "extra file(s)" picker.
const MULTI_FILE_TOOLS = new Set([
  "pdf_merge", "video_merge", "audio_merge", "pdf_compare", "subtitle_burn",
]);

interface Props {
  token: string | null;
  onRun?: (toolName: string, result: JobResult) => void;
}

/**
 * Frontend tool browser + runner: lists tools from the API catalog by
 * category, lets the user pick one, upload a file (plus extra files and
 * JSON options for tools that need them), and posts it to
 * /api/tools/{tool}/process. This is the UI counterpart to the backend's
 * ToolRouter (apps/api/services/tool_router.py) — same "data drives the
 * catalog" idea, so adding a tool server-side surfaces it here for free.
 */
export default function ToolRouter({ token, onRun }: Props) {
  const [category, setCategory] = useState<ToolCategory>("pdf");
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [extraFiles, setExtraFiles] = useState<File[]>([]);
  const [optionsText, setOptionsText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadName, setDownloadName] = useState<string | null>(null);

  useEffect(() => {
    api.listTools(category).then((res) => setTools(res.tools));
    // The previous category's selected tool isn't valid once the tool
    // list has changed underneath it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedTool(null);
  }, [category]);

  useEffect(() => {
    // Clears the previous tool's run result/status when switching tools,
    // so leftover output from tool A can't be mistaken for tool B's.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDownloadUrl(null);
    setError(null);
    setStatusText(null);
  }, [selectedTool]);

  async function run() {
    if (!token || !selectedTool || !file) return;
    setBusy(true);
    setError(null);
    setDownloadUrl(null);
    setStatusText(null);
    try {
      let options: Record<string, unknown> = {};
      try {
        options = JSON.parse(optionsText || "{}");
      } catch {
        throw new Error("Options must be valid JSON");
      }
      let result = await api.processTool(selectedTool, file, token, options, extraFiles);

      if (result.isAsync && (result.status === "pending" || result.status === "processing")) {
        // Video-category and document-conversion tools run on the
        // background worker (see docs/engines.md) — this is expected to
        // take longer than a normal request, so poll rather than treat
        // the initial `pending` as a final answer.
        setStatusText("Processing in the background — this tool can take a while…");
        result = await api.pollJob(result.jobId, token);
      }

      if (result.status === "failed") {
        throw new Error(result.error ?? "Processing failed");
      }

      setStatusText(null);
      setDownloadUrl(result.downloadUrl ?? null);
      setDownloadName(result.filename ?? null);
      onRun?.(selectedTool, result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={styles.tabs}>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            style={{
              ...styles.tab,
              background: category === c ? "var(--accent)" : "var(--surface-2)",
              color: category === c ? "#12151c" : "var(--text)",
            }}
          >
            {c}
          </button>
        ))}
      </div>

      <div style={styles.toolGrid}>
        {tools.map((t) => (
          <button
            key={t.name}
            onClick={() => setSelectedTool(t.name)}
            style={{
              ...styles.toolCard,
              borderColor: selectedTool === t.name ? "var(--accent)" : "var(--border)",
            }}
          >
            <div style={{ fontWeight: 600 }}>{t.label}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {t.base_credits} credits{t.is_async ? " · background job" : ""}
            </div>
          </button>
        ))}
      </div>

      {selectedTool && (
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10, maxWidth: 480 }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

          {MULTI_FILE_TOOLS.has(selectedTool) && (
            <label style={styles.hint}>
              Additional file(s) this tool needs (e.g. the second PDF to merge/compare, or an .srt for
              subtitle burn):
              <input
                type="file"
                multiple
                onChange={(e) => setExtraFiles(Array.from(e.target.files ?? []))}
              />
            </label>
          )}

          <label style={styles.hint}>
            Options (JSON) — see docs/engines.md for what this tool reads, e.g.{" "}
            {"{"}&quot;angle&quot;: 180{"}"}
            <textarea
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              rows={2}
              style={styles.textarea}
            />
          </label>

          <button disabled={!token || !file || busy} onClick={run} style={styles.runButton}>
            {busy ? "Processing…" : token ? "Run tool" : "Sign in to run"}
          </button>

          {statusText && <p style={{ color: "var(--text-muted)", margin: 0 }}>{statusText}</p>}
          {error && <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
          {downloadUrl && (
            <a href={downloadUrl} download={downloadName ?? undefined} style={styles.downloadLink}>
              Download result{downloadName ? ` — ${downloadName}` : ""}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  tabs: { display: "flex", gap: 8, marginBottom: 16 },
  tab: {
    padding: "8px 16px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    fontWeight: 600,
    textTransform: "capitalize",
  },
  toolGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
    gap: 10,
  },
  toolCard: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: 14,
    textAlign: "left",
    color: "var(--text)",
  },
  hint: { fontSize: 12, color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: 4 },
  textarea: {
    fontFamily: "monospace",
    fontSize: 12,
    padding: 8,
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--surface)",
    color: "var(--text)",
    resize: "vertical",
  },
  runButton: {
    padding: "10px 20px",
    borderRadius: 8,
    border: "none",
    background: "var(--accent)",
    color: "#12151c",
    fontWeight: 700,
    alignSelf: "flex-start",
  },
  downloadLink: {
    color: "var(--success)",
    fontWeight: 600,
    textDecoration: "underline",
  },
};
