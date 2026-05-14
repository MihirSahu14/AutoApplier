import { createContext, useContext, useState, useCallback, ReactNode } from "react";

type Toast = { id: number; kind: "ok" | "err" | "info"; msg: string };
const Ctx = createContext<{
  toast: (msg: string, kind?: Toast["kind"]) => void;
} | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = useCallback((msg: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-2 rounded-md shadow-2xl text-sm border ${
              t.kind === "ok"
                ? "bg-emerald-600/10 text-emerald-200 border-emerald-500/30"
                : t.kind === "err"
                ? "bg-red-600/10 text-red-200 border-red-500/30"
                : "bg-slate-800/70 text-slate-200 border-slate-700"
            }`}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be inside ToastProvider");
  return ctx.toast;
}
