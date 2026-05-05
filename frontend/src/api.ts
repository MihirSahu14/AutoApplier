// API client for the FastAPI backend.

export type Job = {
  id: number;
  source: string;
  company: string;
  title: string | null;
  location: string | null;
  url: string;
  posted_at: string | null;
  score: number | null;
  fit_summary: string | null;
  disqualified: number | null;
  disqualify_reason: string | null;
  app_status: string | null;
  resume_path: string | null;
  cover_letter_path: string | null;
  notes: string | null;
};

export type JobDetail = Job & {
  description: string;
  have_resume: boolean;
  have_cover: boolean;
  cover_text: string | null;
};

export type Budget = {
  stages: { name: string; cap: number; spent: number; remaining: number; pct: number }[];
  daily: number;
  total_today: number;
  running: string[];
};

export type Meta = {
  sources: string[];
  statuses: string[];
  counts: { total: number; scored: number; qualified: number; applied: number };
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

export const api = {
  budget: () => req<Budget>("/api/budget"),
  meta: () => req<Meta>("/api/meta"),
  jobs: (params: Record<string, string | number | boolean | undefined>) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "" && v !== false) q.set(k, String(v));
    });
    return req<{ jobs: Job[] }>(`/api/jobs?${q.toString()}`);
  },
  job: (id: number) => req<JobDetail>(`/api/jobs/${id}`),
  setStatus: (id: number, status: string, notes?: string) =>
    req<{ ok: true }>(`/api/jobs/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, notes: notes ?? null }),
    }),
  tailor: (id: number, no_cover = false) =>
    req<{ ok: true; tailoring_spent_today: number }>(
      `/api/jobs/${id}/tailor?no_cover=${no_cover}`,
      { method: "POST" }
    ),
  openJob: (id: number) =>
    req<{ ok: true }>(`/api/jobs/${id}/open`, { method: "POST" }),
  runIngest: () => req<{ started: boolean }>("/api/run/ingest", { method: "POST" }),
  runPrefilter: () => req<{ started: boolean }>("/api/run/prefilter", { method: "POST" }),
  runScore: () => req<{ started: boolean }>("/api/run/score", { method: "POST" }),
  runExport: () => req<{ path: string }>("/api/run/export", { method: "POST" }),
};

export const downloadUrl = (id: number, kind: "resume" | "cover") =>
  `/api/jobs/${id}/download/${kind}`;
