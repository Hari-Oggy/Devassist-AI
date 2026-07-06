export function ThreadBadge({ status }: { status: "local" | "pending" | "submitted" }) {
  const map = {
    local: "bg-white/10 text-white/70",
    pending: "bg-amber-500/10 text-amber-500",
    submitted: "bg-emerald-500/10 text-emerald-500",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${map[status]}`}>
      {status}
    </span>
  );
}
