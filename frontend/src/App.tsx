import { Outlet, Link, useLocation, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function App() {
  const loc = useLocation();
  const { data: budget } = useQuery({
    queryKey: ["budget"],
    queryFn: api.budget,
    refetchInterval: (q) =>
      (q.state.data?.running?.length ?? 0) > 0 ? 1500 : 8000,
  });
  const { data: setup, isLoading: setupLoading } = useQuery({
    queryKey: ["setup-status"],
    queryFn: api.setupStatus,
  });

  if (setupLoading) {
    return <div className="p-8 text-slate-400 text-sm">Loading…</div>;
  }
  if (setup && !setup.configured && loc.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }

  const showHeaderBudget = setup?.configured;

  return (
    <div className="min-h-full">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <Link to="/" className="text-xl font-bold flex items-center gap-2">
            <span className="inline-block w-7 h-7 rounded bg-slate-900 text-white text-center leading-7 text-sm">A</span>
            Auto Job Applier
          </Link>
          <div className="flex flex-wrap gap-2 text-sm items-center">
            {budget?.running?.length ? (
              <span className="px-2 py-1 bg-amber-100 text-amber-900 rounded text-xs animate-pulse">
                running: {budget.running.join(", ")}
              </span>
            ) : null}
            {showHeaderBudget && budget?.stages.map((s) => (
              <div key={s.name} className="px-3 py-1 bg-slate-100 rounded text-xs">
                <span className="text-slate-500">{s.name}</span>{" "}
                <span className="font-mono">${s.spent.toFixed(3)}</span>
                <span className="text-slate-400"> / ${s.cap.toFixed(2)}</span>
              </div>
            ))}
            {showHeaderBudget && budget && (
              <div className="px-3 py-1 bg-slate-900 text-white rounded font-mono text-xs">
                ${budget.total_today.toFixed(3)} today
              </div>
            )}
            {setup?.configured && (
              <Link to="/settings" title="Settings"
                    className="px-2 py-1 text-slate-500 hover:text-slate-900">
                ⚙
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
