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

  type ActionKey = "ingest" | "ingest-hn" | "ingest-gh" | "ingest-lever" | "ingest-ashby" | "prefilter" | "score" | "export";
  const action = useMutation({
    mutationFn: async (kind: ActionKey) => {
      if (kind === "ingest")        return { ...(await api.runIngest("all")),         label: "Ingest (all)" };
      if (kind === "ingest-hn")     return { ...(await api.runIngest("hn")),          label: "Ingest HN" };
      if (kind === "ingest-gh")     return { ...(await api.runIngest("greenhouse")),  label: "Ingest Greenhouse" };
      if (kind === "ingest-lever")  return { ...(await api.runIngest("lever")),       label: "Ingest Lever" };
      if (kind === "ingest-ashby")  return { ...(await api.runIngest("ashby")),       label: "Ingest Ashby" };
      if (kind === "prefilter")     return { ...(await api.runPrefilter()),           label: "Pre-filter" };
      if (kind === "score")         return { ...(await api.runScore()),               label: "Scoring" };
      const r = await api.runExport();
      return { started: true, path: r.path, label: "Export" };
    },
    onSuccess: (r: any) => {
      if (r.path) toast(`Exported to ${r.path}`);
      else if (r.started) toast(`${r.label} started — running in background`);
      else toast(`${r.label} already running`, "info");
      refreshAll();
    },
    onError: (e: any) => toast(`Failed: ${e.message}`, "err"),
  });

  const noJobsYet = !jobs.isLoading && (meta.data?.counts.total ?? 0) === 0;

  return (
    <>
      {/* Hero */}
      <div className="hero-gradient rounded-2xl p-10 mb-6 shadow-xl">
        <h1 className="text-5xl font-extrabold text-white tracking-tight">Welcome back.</h1>
        <p className="text-slate-200/90 mt-3 max-w-2xl">
          Find, rate, tailor, and reach out to the right people — your end-to-end
          job-search pipeline in one place.
        </p>
        <div className="flex flex-wrap gap-3 mt-6">
          <div className="relative inline-block group">
            <PrimaryBtn onClick={() => action.mutate("ingest")}>
              Ingest jobs ▾
            </PrimaryBtn>
            <div className="hidden group-hover:block absolute top-full left-0 mt-1 z-20 bg-[#11121c] border border-slate-800 rounded-lg shadow-2xl py-1 min-w-[200px]">
              {([
                ["ingest", "All sources"],
                ["ingest-hn", "HN Who-is-hiring"],
                ["ingest-gh", "Greenhouse companies"],
                ["ingest-lever", "Lever companies"],
                ["ingest-ashby", "Ashby companies"],
              ] as [ActionKey, string][]).map(([key, label]) => (
                <button key={key} onClick={() => action.mutate(key)}
                        className="block w-full text-left px-3 py-2 text-sm text-slate-200 hover:bg-slate-800/80">
                  {label}
                </button>
              ))}
            </div>
          </div>
          <SecondaryBtn onClick={() => action.mutate("prefilter")}>Pre-filter (free)</SecondaryBtn>
          <SecondaryBtn onClick={() => action.mutate("score")}>Score</SecondaryBtn>
          <SecondaryBtn onClick={() => action.mutate("export")}>Export</SecondaryBtn>
        </div>
      </div>

      {/* Counters */}
      {meta.data && !noJobsYet && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <Stat label="Total ingested" value={meta.data.counts.total} />
          <Stat label="Scored" value={meta.data.counts.scored} />
          <Stat label="Qualified" value={meta.data.counts.qualified} accent="text-indigo-400" />
          <Stat label="Applied" value={meta.data.counts.applied} accent="text-emerald-400" />
        </div>
      )}

      {noJobsYet ? (
        <Card>
          <div className="p-10 text-center">
            <div className="text-5xl mb-3">📭</div>
            <h2 className="text-lg font-semibold text-slate-100">No jobs yet</h2>
            <p className="text-sm text-slate-400 mt-1">
              Click <strong className="text-slate-200">Ingest jobs</strong> above to pull
              the latest postings. Then run Pre-filter + Score to rank them.
            </p>
          </div>
        </Card>
      ) : (
        <>
          {/* Filter bar */}
          <Card className="p-4 mb-4">
            <form
              onSubmit={(e) => { e.preventDefault(); jobs.refetch(); }}
              className="flex flex-wrap gap-2 items-center"
            >
              <input
                type="text" placeholder="Search company / title / description"
                value={filters.q}
                onChange={(e) => setFilters({ ...filters, q: e.target.value })}
                className="px-3 py-2 border border-slate-800 rounded text-sm flex-1 min-w-[220px]"
              />
              <input
                type="number" min={0} max={100}
                value={filters.min_score}
                onChange={(e) => setFilters({ ...filters, min_score: +e.target.value })}
                className="px-3 py-2 border border-slate-800 rounded text-sm w-28"
                title="Min score"
              />
              <select
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                className="px-3 py-2 border border-slate-800 rounded text-sm"
              >
                <option value="">— any status —</option>
                {meta.data?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <select
                value={filters.source}
                onChange={(e) => setFilters({ ...filters, source: e.target.value })}
                className="px-3 py-2 border border-slate-800 rounded text-sm"
              >
                <option value="">— any source —</option>
                {meta.data?.sources.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <label className="flex items-center gap-1 text-sm text-slate-400">
                <input
                  type="checkbox" checked={filters.include_dq}
                  onChange={(e) => setFilters({ ...filters, include_dq: e.target.checked })}
                />
                Show disqualified
              </label>
            </form>
          </Card>

          <div className="text-sm text-slate-500 mb-2">
            {jobs.data?.jobs.length ?? 0} jobs
          </div>

          <Card>
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-xs uppercase border-b border-slate-800">
                <tr>
                  <th className="px-3 py-3 text-right">Score</th>
                  <th className="px-3 py-3 text-left">Company</th>
                  <th className="px-3 py-3 text-left">Title</th>
                  <th className="px-3 py-3 text-left">Location</th>
                  <th className="px-3 py-3 text-left">Status</th>
                  <th className="px-3 py-3 text-left">Why</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data?.jobs.map((j) => (
                  <tr key={j.id} className="border-t border-slate-800 hover:bg-indigo-500/5">
                    <td className="px-3 py-3 text-right"><ScorePill score={j.score} /></td>
                    <td className="px-3 py-3 font-medium">
                      <Link to={`/jobs/${j.id}`} className="text-slate-100 hover:text-indigo-400">
                        {j.company}
                      </Link>
                    </td>
                    <td className="px-3 py-3 text-slate-300">{j.title}</td>
                    <td className="px-3 py-3 text-slate-500">{j.location}</td>
                    <td className="px-3 py-3">
                      {j.app_status ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                          {j.app_status}
                        </span>
                      ) : <span className="text-slate-600 text-xs">—</span>}
                    </td>
                    <td className="px-3 py-3 text-slate-400 text-xs max-w-md">{j.fit_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.isLoading && <div className="p-6 text-center text-slate-500">Loading…</div>}
            {jobs.data && jobs.data.jobs.length === 0 && (
              <div className="p-10 text-center text-slate-500 text-sm">No jobs match these filters.</div>
            )}
          </Card>
        </>
      )}
    </>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="bg-[#11121c] border border-slate-800 rounded-lg p-4">
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${accent || "text-slate-100"}`}>{value}</div>
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#11121c] border border-slate-800 rounded-lg overflow-hidden ${className}`}>
      {children}
    </div>
  );
}

function PrimaryBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-sm font-medium shadow-lg shadow-indigo-600/20">
      {children}
    </button>
  );
}

function SecondaryBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
            className="px-4 py-2 bg-white/10 hover:bg-white/15 border border-white/20 text-white rounded-md text-sm font-medium">
      {children}
    </button>
  );
}
