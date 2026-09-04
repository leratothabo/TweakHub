/**
 * VESTIGIAL. AVX was never confirmed as a real maintained project (see
 * docs/engines.md) — the image/video/audio/pdf-text conversions this was
 * meant to front are now handled by
 * apps/api/services/engines/media_convert.py (Pillow, ffmpeg,
 * poppler-utils), called from apps/web via api.processTool() in lib/api.ts.
 *
 * There IS a real background-job-queue now (apps/api/services/job_queue.py
 * + job_worker.py, RQ + Redis) for the tools slow enough to need one
 * (video-category tools, plus everything the `document` engine handles —
 * see routes/tools.py's ASYNC_TOOL_NAMES), with real status polling
 * (routes/jobs.py, GET /api/jobs/{id}, wrapped by api.pollJob() in
 * lib/api.ts). It just doesn't look anything like AvxJobStatus below —
 * the real shape is api.JobResult in lib/api.ts. This file is kept purely
 * as a historical marker of what AVX was supposed to be, not because
 * anything still needs it.
 */
export interface AvxJobStatus {
  jobId: string;
  status: "queued" | "processing" | "done" | "failed";
  progress?: number;
}

export class AvxClient {
  constructor(private readonly baseUrl: string) {}

  async getJobStatus(jobId: string): Promise<AvxJobStatus> {
    const res = await fetch(`${this.baseUrl}/jobs/${jobId}`);
    if (!res.ok) throw new Error(`AVX status check failed: ${res.status}`);
    return res.json();
  }
}
