export function ScorePill({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined)
    return <span className="text-slate-300 text-sm">—</span>;
  const cls =
    score >= 90 ? "bg-green-100 text-green-900" :
    score >= 80 ? "bg-lime-100 text-lime-900" :
    score >= 70 ? "bg-yellow-100 text-yellow-900" :
    score >= 50 ? "bg-amber-100 text-amber-900" :
                  "bg-red-100 text-red-900";
  return (
    <span className={`px-2 py-0.5 rounded-full text-sm font-semibold ${cls}`}>
      {score}
    </span>
  );
}
