import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ScorePill } from "../components/ScorePill";
import { useToast } from "../components/Toast";

export function JobList() {
  const [filters, setFilters] = useState({
    min_score: 70, status: "", source: "", q: "", include_dq: false,
  });

  const qc = useQueryClient();
  const toast = useToast();
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const jobs = useQuery({
    queryKey: ["jobs", filters],
    queryFn: () => api.jobs(filters),
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ["jobs"] });
    qc.invalidateQueries({ queryKey: ["meta"] });
    qc.invalidateQueries({ queryKey: ["budget"] });
  };

  const action = useMutation({
    mutationFn: async (kind: "ingest" | "prefilter" | "score" | "export") => {
      if (kind === "ingest")    return { ...(await api.runIngest()),    label: "Ingest"    };
      if (kind === "prefilter") return { ...(await api.runPrefilter()), label: "Pre-filter" };
      if (kind === "score")     return { ...(await api.runScore()),     label: "Scoring"   };
      const r = await api.runExport();
      return { started: true, path: r.path, label: "Export" };
    },
    onSuccess: (r: any) => {
      if (r.path) toast(`Exported to ${r.path}`);
      else if (r.started) toast(`${r.label} started — running in background`);
      else toast(`${r.label} is already running`, "info");
      refreshAll();
    },
    onError: (e: any) => toast(`Failed: ${e.message}`, "err"),
  });

  const noJobsYet = !jobs.isLoading && (meta.data?.counts.total ?? 0) === 0;

  return (
    <>
      <div className="flex flex-wrap gap-2 mb-4">
        <Btn onClick={() => action.mutate("ingest")} cls="bg-blue-600 hover:bg-blue-700">
          Ingest HN
        </Btn>
        <Btn onClick={() => action.mutate("prefilter")} cls="bg-slate-700 hover:bg-slate-800">
          Pre-filter (free)
        </Btn>
        <Btn onClick={() => action.mutate("score")} cls="bg-purple-600 hover:bg-purple-700">
          Score unscored
        </Btn>
        <Btn onClick={() => action.mutate("export")} cls="bg-emerald-600 hover:bg-emerald-700">
          Export to Excel
        </Btn>
        {meta.data && !noJobsYet && (
          <div className="text-xs text-slate-500 ml-2 self-center">
            {meta.data.counts.qualified} qualified · {meta.data.counts.applied} applied · {meta.data.counts.total} total
          </div>
        )}
      </div>

      {noJobsYet ? (
        <div className="bg-white border border-dashed border-slate-300 rounded p-10 text-center">
          <div className="text-5xl mb-3">📭</div>
          <h2 className="text-lg font-semibold">No jobs yet</h2>
          <p className="text-sm text-slate-500 mt-1 mb-4">
            Click <strong>Ingest HN</strong> above to pull the latest
            "Who is hiring?" jobs, then <strong>Pre-filter</strong> +
            <strong> Score</strong> to rank them against your resume.
          </p>
        </div>
      ) : (
        <>
          <form
            onSubmit={(e) => { e.preventDefault(); jobs.refetch(); }}
            className="flex flex-wrap gap-2 mb-4 bg-white p-3 rounded shadow-sm border border-slate-200"
          >
            <input
              type="text" placeholder="Search company / title / desc"
              value={filters.q}
              onChange={(e) => setFilters({ ...filters, q: e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded text-sm flex-1 min-w-[220px]"
            />
            <input
              type="number" min={0} max={100}
              value={filters.min_score}
              onChange={(e) => setFilters({ ...filters, min_score: +e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded text-sm w-28"
              title="Min score"
            />
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded text-sm"
            >
              <option value="">— any status —</option>
              {meta.data?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select
              value={filters.source}
              onChange={(e) => setFilters({ ...filters, source: e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded text-sm"
            >
              <option value="">— any source —</option>
              {meta.data?.sources.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox" checked={filters.include_dq}
                onChange={(e) => setFilters({ ...filters, include_dq: e.target.checked })}
              />
              Show disqualified
            </label>
          </form>

          <div className="text-sm text-slate-500 mb-2">
            {jobs.data?.jobs.length ?? 0} jobs
          </div>

          <div className="bg-white border border-slate-200 rounded shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-right">Score</th>
                  <th className="px-3 py-2 text-left">Company</th>
                  <th className="px-3 py-2 text-left">Title</th>
                  <th className="px-3 py-2 text-left">Location</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Why</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data?.jobs.map((j) => (
                  <tr key={j.id} className="border-t border-slate-100 hover:bg-blue-50">
                    <td className="px-3 py-2 text-right"><ScorePill score={j.score} /></td>
                    <td className="px-3 py-2 font-medium">
                      <Link to={`/jobs/${j.id}`} className="hover:underline">{j.company}</Link>
                    </td>
                    <td className="px-3 py-2">{j.title}</td>
                    <td className="px-3 py-2 text-slate-500">{j.location}</td>
                    <td className="px-3 py-2">
                      {j.app_status ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-100 border border-slate-200">
                          {j.app_status}
                        </span>
                      ) : <span className="text-slate-300 text-xs">—</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-600 text-xs max-w-md">{j.fit_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.isLoading && <div className="p-6 text-center text-slate-400">Loading…</div>}
            {jobs.data && jobs.data.jobs.length === 0 && (
              <div className="p-6 text-center text-slate-400">No jobs match these filters.</div>
            )}
          </div>
        </>
      )}
    </>
  );
}

function Btn({ children, onClick, cls }: { children: React.ReactNode; onClick: () => void; cls: string }) {
  return (
    <button type="button" onClick={onClick}
            className={`px-3 py-2 text-white rounded text-sm ${cls}`}>
      {children}
    </button>
  );
}
