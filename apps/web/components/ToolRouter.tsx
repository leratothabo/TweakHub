"use client";

import { useEffect, useState } from "react";
import { api, JobResult, ToolCategory, ToolSummary } from "@/lib/api";
import {
  IconAudio,
  IconCheck,
  IconDocument,
  IconImage,
  IconPdf,
  IconUpload,
  IconVideo,
} from "@/components/icons/Icons";

const CATEGORIES: { key: ToolCategory; label: string; icon: typeof IconPdf }[] = [
  { key: "pdf", label: "PDF", icon: IconPdf },
  { key: "image", label: "Image", icon: IconImage },
  { key: "video", label: "Video", icon: IconVideo },
  { key: "audio", label: "Audio", icon: IconAudio },
  { key: "document", label: "Document", icon: IconDocument },
];

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
      <div className="category-tabs">
        {CATEGORIES.map((c) => {
          const active = category === c.key;
          return (
            <button
              key={c.key}
              onClick={() => setCategory(c.key)}
              className="category-tab"
              style={{
                background: active ? "var(--accent-fill)" : "var(--surface-2)",
                color: active ? "var(--on-accent)" : "var(--text-muted)",
                borderColor: active ? "transparent" : "var(--border)",
              }}
            >
              <c.icon size={16} />
              {c.label}
            </button>
          );
        })}
      </div>

      <div className="tool-grid">
        {tools.map((t) => (
          <button
            key={t.name}
            onClick={() => setSelectedTool(t.name)}
            className="card card-hover tool-card"
            style={{
              borderColor: selectedTool === t.name ? "var(--accent-2)" : "var(--border)",
              boxShadow: selectedTool === t.name ? "0 0 0 1px var(--accent-2)" : undefined,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 14.5 }}>{t.label}</div>
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6, fontFamily: "var(--font-mono)" }}>
              {t.base_credits} credits{t.is_async ? " · background job" : ""}
            </div>
          </button>
        ))}
        {tools.length === 0 && (
          <div style={{ color: "var(--text-dim)", fontSize: 13.5, padding: "8px 2px" }}>Loading tools…</div>
        )}
      </div>

      {selectedTool && (
        <div className="card" style={{ marginTop: 24, padding: 24, maxWidth: 520 }}>
          <label htmlFor="tool-file" className="dropzone">
            <IconUpload size={22} color="var(--accent-2)" />
            <span style={{ fontWeight: 700, fontSize: 14 }}>
              {file ? file.name : "Choose a file or drag it here"}
            </span>
            <input
              id="tool-file"
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ display: "none" }}
            />
          </label>

          {MULTI_FILE_TOOLS.has(selectedTool) && (
            <label style={styles.hint}>
              Additional file(s) this tool needs (e.g. the second PDF to merge/compare, or an .srt for
              subtitle burn):
              <input
                type="file"
                multiple
                onChange={(e) => setExtraFiles(Array.from(e.target.files ?? []))}
                style={{ marginTop: 4 }}
              />
            </label>
          )}

          <label style={{ ...styles.hint, marginTop: 14 }}>
            Options (JSON) — see docs/engines.md for what this tool reads, e.g.{" "}
            {"{"}&quot;angle&quot;: 180{"}"}
            <textarea
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              rows={2}
              style={styles.textarea}
            />
          </label>

          <button disabled={!token || !file || busy} onClick={run} className="btn btn-primary" style={{ marginTop: 16, width: "100%" }}>
            {busy ? "Processing…" : token ? "Run tool" : "Sign in to run"}
          </button>

          {statusText && <p style={{ color: "var(--text-muted)", fontSize: 13.5, marginTop: 12 }}>{statusText}</p>}
          {error && <p style={{ color: "var(--danger)", fontSize: 13.5, marginTop: 12 }}>{error}</p>}
          {downloadUrl && (
            <a href={downloadUrl} download={downloadName ?? undefined} className="result-banner">
              <IconCheck size={17} color="var(--success)" />
              <span>
                Ready — download {downloadName ? <strong>{downloadName}</strong> : "your result"}
              </span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  hint: { fontSize: 12, color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: 4 },
  textarea: {
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    padding: 8,
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    color: "var(--text)",
    resize: "vertical",
  },
};
