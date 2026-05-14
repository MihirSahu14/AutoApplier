import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, downloadUrl } from "../api";
import { ScorePill } from "../components/ScorePill";
import { useToast } from "../components/Toast";
import { Outreach } from "../components/Outreach";

export function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const qc = useQueryClient();

  const toast = useToast();
  const job = useQuery({ queryKey: ["job", jobId], queryFn: () => api.job(jobId) });
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });

  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [applyUrl, setApplyUrl] = useState("");
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
      toast("Package generated", "ok");
    },
    onError: (e: any) => toast(e.message, "err"),
  });

  const save = useMutation({
    mutationFn: () => api.setStatus(jobId, status, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      toast("Saved", "ok");
    },
  });

  const open = useMutation({ mutationFn: () => api.openJob(jobId) });
  const autofill = useMutation({
    mutationFn: () => api.autofill(jobId, applyUrl.trim() || undefined),
    onSuccess: () => toast("Browser launching… review and submit when ready.", "ok"),
    onError: (e: any) => toast(e.message, "err"),
  });

  if (job.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (!job.data) return <div className="text-red-400">Job not found.</div>;
  const j = job.data;

  return (
    <>
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-200">← back to jobs</Link>

      <Card className="p-6 mt-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wide">{j.source}</div>
            <h1 className="text-3xl font-bold mt-1 text-slate-100">{j.company}</h1>
            <div className="text-slate-300 mt-1">{j.title}</div>
            <div className="text-sm text-slate-500 mt-1">{j.location}</div>
          </div>
          <div className="text-right">
            <ScorePill score={j.score} />
            {j.disqualified ? (
              <div className="text-xs text-red-300 mt-2">DQ: {j.disqualify_reason}</div>
            ) : null}
          </div>
        </div>

        {j.fit_summary && (
          <p className="mt-4 text-sm text-slate-400 italic">{j.fit_summary}</p>
        )}

        <div className="flex flex-wrap gap-2 mt-5">
          <Btn onClick={() => open.mutate()} cls="bg-slate-700 hover:bg-slate-600">
            Open job page ↗
          </Btn>
          <Btn
            onClick={() => tailor.mutate()}
            disabled={tailor.isPending}
            cls="bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/20"
          >
            {tailor.isPending ? "Generating…" : (j.have_resume ? "Re-generate package" : "Generate package")}
          </Btn>
          {j.have_resume && (
            <a href={downloadUrl(jobId, "resume")}
               className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-sm font-medium">
              Download Resume
            </a>
          )}
          {j.have_cover && (
            <a href={downloadUrl(jobId, "cover")}
               className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-sm font-medium">
              Download Cover Letter
            </a>
          )}
        </div>

        {/* Autofill */}
        <div className="mt-6 border-t border-slate-800 pt-4">
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            Open & autofill application
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <input
              type="text" value={applyUrl}
              onChange={(e) => setApplyUrl(e.target.value)}
              placeholder={`Apply URL (leave blank to use: ${j.url || "—"})`}
              className="flex-1 min-w-[260px] px-3 py-2 border border-slate-800 rounded text-sm"
            />
            <Btn
              onClick={() => autofill.mutate()}
              disabled={autofill.isPending || !j.have_resume}
              cls="bg-fuchsia-600 hover:bg-fuchsia-500"
            >
              {autofill.isPending ? "Launching…" : "Open with autofill"}
            </Btn>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Opens a real Chromium window with your tailored resume uploaded and standard fields prefilled.
            Logins persist across runs. <strong>Nothing is submitted</strong> — you review and click apply.
          </p>
        </div>
      </Card>

      <div className="grid md:grid-cols-2 gap-4 mt-4">
        <Card className="p-5">
          <h2 className="font-semibold text-slate-100 mb-3">Application status</h2>
          <label className="block text-xs uppercase text-slate-400 mb-1">Status</label>
          <select
            value={status} onChange={(e) => setStatus(e.target.value)}
            className="w-full px-3 py-2 border border-slate-800 rounded text-sm mb-3"
          >
            {meta.data?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="block text-xs uppercase text-slate-400 mb-1">Notes</label>
          <textarea
            rows={4} value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full px-3 py-2 border border-slate-800 rounded text-sm mb-3"
            placeholder="Recruiter contact, interview notes, anything to remember…"
          />
          <Btn onClick={() => save.mutate()} cls="bg-slate-700 hover:bg-slate-600">
            {save.isPending ? "Saving…" : "Save"}
          </Btn>
        </Card>

        <Card className="p-5">
          <h2 className="font-semibold text-slate-100 mb-3">Cover letter preview</h2>
          {j.cover_text ? (
            <pre className="text-sm leading-relaxed text-slate-300">{j.cover_text}</pre>
          ) : (
            <p className="text-sm text-slate-500">Not generated yet. Click "Generate package".</p>
          )}
        </Card>
      </div>

      <Outreach jobId={jobId} />

      <Card className="p-5 mt-4">
        <h2 className="font-semibold text-slate-100 mb-3">Job description</h2>
        <pre className="text-sm leading-relaxed text-slate-300">{j.description}</pre>
      </Card>
    </>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#11121c] border border-slate-800 rounded-lg ${className}`}>
      {children}
    </div>
  );
}

function Btn({ children, onClick, cls = "", disabled }: {
  children: React.ReactNode; onClick: () => void; cls?: string; disabled?: boolean
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}
            className={`px-4 py-2 text-white rounded-md text-sm font-medium disabled:opacity-50 ${cls}`}>
      {children}
    </button>
  );
}
