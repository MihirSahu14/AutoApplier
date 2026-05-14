export function ScorePill({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined)
    return <span className="text-slate-600 text-sm">—</span>;
  const cls =
    score >= 90 ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" :
    score >= 80 ? "bg-lime-500/15   text-lime-300   border border-lime-500/30"     :
    score >= 70 ? "bg-yellow-500/15 text-yellow-300 border border-yellow-500/30"   :
    score >= 50 ? "bg-amber-500/15  text-amber-300  border border-amber-500/30"    :
                  "bg-red-500/15    text-red-300    border border-red-500/30";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {score}
    </span>
  );
}
