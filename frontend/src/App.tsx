import { useEffect, useState } from "react";
import { Outlet, Link, NavLink, useLocation, Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, restoreProfileIfNeeded } from "./api";

export function App() {
  const loc = useLocation();
  const qc = useQueryClient();
  const [restoring, setRestoring] = useState(true);

  // On boot: if the (free-tier, ephemeral) backend has lost the profile but
  // we have a copy in localStorage, push it back transparently.
  // Cap the whole attempt at 12 s — Render free cold-starts can take 30–60 s,
  // so we give up and let the normal queries surface a real error instead of
  // leaving the user staring at "Loading…" forever.
  useEffect(() => {
    let cancelled = false;
    const deadline = new Promise<false>((res) => setTimeout(() => res(false), 12_000));
    (async () => {
      try {
        const restored = await Promise.race([restoreProfileIfNeeded(), deadline]);
        if (!cancelled && restored) {
          qc.invalidateQueries({ queryKey: ["setup-status"] });
          qc.invalidateQueries({ queryKey: ["profile"] });
        }
      } catch { /* offline or cold start — queries below will surface the error */ }
      finally { if (!cancelled) setRestoring(false); }
    })();
    return () => { cancelled = true; };
  }, [qc]);

  const { data: budget } = useQuery({
    queryKey: ["budget"],
    queryFn: api.budget,
    enabled: !restoring,
    refetchInterval: (q) =>
      (q.state.data?.running?.length ?? 0) > 0 ? 1500 : 8000,
  });
  const { data: setup, isLoading: setupLoading } = useQuery({
    queryKey: ["setup-status"],
    queryFn: api.setupStatus,
    enabled: !restoring,
  });

  if (restoring || setupLoading) {
    return <WakingUp />;
  }
  if (setup && !setup.configured && loc.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }

  return (
    <div className="min-h-full">
      <header className="bg-[#0d0e16] border-b border-slate-800 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
          <Link to="/" className="text-2xl font-extrabold tracking-tight flex items-center gap-2">
            <span className="bg-gradient-to-br from-indigo-500 to-violet-600 bg-clip-text text-transparent">
              AutoApplier
            </span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <NavItem to="/" end>Jobs</NavItem>
            <NavItem to="/settings">Settings</NavItem>
          </nav>
          <div className="flex flex-wrap gap-2 items-center">
            {budget?.running?.length ? (
              <span className="px-2 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded text-xs animate-pulse">
                running: {budget.running.join(", ")}
              </span>
            ) : null}
            {setup?.configured && budget?.stages.map((s) => (
              <div key={s.name} className="px-2.5 py-1 bg-slate-900/70 border border-slate-800 rounded text-xs">
                <span className="text-slate-400">{s.name}</span>{" "}
                <span className="font-mono text-slate-200">${s.spent.toFixed(3)}</span>
                <span className="text-slate-600"> / ${s.cap.toFixed(2)}</span>
              </div>
            ))}
            {setup?.configured && budget && (
              <div className="px-3 py-1 bg-indigo-600 text-white rounded font-mono text-xs">
                ${budget.total_today.toFixed(3)} today
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}

function WakingUp() {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 4000); return () => clearTimeout(t); }, []);
  return (
    <div className="min-h-screen bg-[#0a0a10] flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
      <p className="text-slate-400 text-sm">
        {slow
          ? "Backend is waking up (Render free tier cold start — ~30 s)…"
          : "Connecting…"}
      </p>
    </div>
  );
}

function NavItem({ to, end, children }: { to: string; end?: boolean; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `relative px-3 py-1.5 ${isActive ? "text-indigo-400" : "text-slate-400 hover:text-slate-100"}`
      }
    >
      {({ isActive }) => (
        <>
          {children}
          {isActive && (
            <span className="absolute left-3 right-3 -bottom-[17px] h-[2px] bg-indigo-500 rounded-full" />
          )}
        </>
      )}
    </NavLink>
  );
}
