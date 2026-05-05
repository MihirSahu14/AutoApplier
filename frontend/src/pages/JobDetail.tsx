import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, downloadUrl } from "../api";
import { ScorePill } from "../components/ScorePill";

export function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const qc = useQueryClient();

  const job = useQuery({ queryKey: ["job", jobId], queryFn: () => api.job(jobId) });
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });

  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  useEffect(() => {
    if (job.data) {
      setStatus(job.data.app_status ?? "Not started");
      setNotes(job.data.notes ?? "");
    }
  }, [job.data?.id]);

  const tailor = useMutation({
    mutationFn: () => api.tailor(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const save = useMutation({
    mutationFn: () => api.setStatus(jobId, status, notes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job", jobId] }),
  });

  const open = useMutation({ mutationFn: () => api.openJob(jobId) });

  if (job.isLoading) return <div className="text-slate-400">Loading…</div>;
  if (!job.data) return <div className="text-red-700">Job not found.</div>;
  const j = job.data;

  return (
    <>
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-900">← back</Link>

      <div className="bg-white border border-slate-200 rounded shadow-sm p-5 mt-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500 uppercase">{j.source}</div>
            <h1 className="text-2xl font-bold mt-1">{j.company}</h1>
            <div className="text-slate-700">{j.title}</div>
            <div className="text-sm text-slate-500 mt-1">{j.location}</div>
          </div>
          <div className="text-right">
            <ScorePill score={j.score} />
            {j.disqualified ? (
              <div className="text-xs text-red-700 mt-1">DQ: {j.disqualify_reason}</div>
            ) : null}
          </div>
        </div>

        {j.fit_summary && (
          <p className="mt-3 text-sm text-slate-600 italic">{j.fit_summary}</p>
        )}

        <div className="flex flex-wrap gap-2 mt-4">
          <button
            onClick={() => open.mutate()}
            className="px-3 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            Open job page ↗
          </button>
          <button
            disabled={tailor.isPending}
            onClick={() => tailor.mutate()}
            className="px-3 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50"
          >
            {tailor.isPending
              ? "Generating…"
              : j.have_resume ? "Re-generate package" : "Generate package"}
          </button>
          {j.have_resume && (
            <a href={downloadUrl(jobId, "resume")}
               className="px-3 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700">
              Download Resume
            </a>
          )}
          {j.have_cover && (
            <a href={downloadUrl(jobId, "cover")}
               className="px-3 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700">
              Download Cover Letter
            </a>
          )}
        </div>
        {tailor.error && (
          <div className="mt-3 text-sm text-red-700">{(tailor.error as Error).message}</div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-4 mt-4">
        <div className="bg-white border border-slate-200 rounded shadow-sm p-5">
          <h2 className="font-semibold mb-3">Application status</h2>
          <label className="block text-xs text-slate-500 uppercase mb-1">Status</label>
          <select
            value={status} onChange={(e) => setStatus(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm mb-3"
          >
            {meta.data?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="block text-xs text-slate-500 uppercase mb-1">Notes</label>
          <textarea
            rows={4} value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm mb-3"
            placeholder="Recruiter contact, interview notes, anything to remember…"
          />
          <button
            onClick={() => save.mutate()}
            className="px-3 py-2 bg-slate-900 text-white rounded text-sm"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>

        <div className="bg-white border border-slate-200 rounded shadow-sm p-5">
          <h2 className="font-semibold mb-3">Cover letter preview</h2>
          {j.cover_text ? (
            <pre className="text-sm leading-relaxed text-slate-700">{j.cover_text}</pre>
          ) : (
            <p className="text-sm text-slate-400">Not generated yet. Click "Generate package".</p>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded shadow-sm p-5 mt-4">
        <h2 className="font-semibold mb-2">Job description</h2>
        <pre className="text-sm leading-relaxed text-slate-800">{j.description}</pre>
      </div>
    </>
  );
}
