"use client";

import { useEffect, useState } from "react";
import {
  GitBranch,
  Plus,
  ExternalLink,
  Settings,
  Code2,
  Layers,
  ShieldAlert,
  CheckCircle2,
  X,
  AlertCircle,
} from "lucide-react";
import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";
import { useDashboardStore, Repository } from "@/lib/stores/dashboardStore";
import { PageHeader, GlassCard, LoadingSpinner, StatusBadge } from "@/components/ui/shared";

// Sparkline for each repo card
function Sparkline({ color = "#a855f7" }: { color?: string }) {
  const data = Array.from({ length: 8 }, (_, i) => ({
    v: Math.floor(Math.random() * 60 + 20),
  }));
  return (
    <ResponsiveContainer width={100} height={36}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} />
        <Tooltip
          contentStyle={{ display: "none" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

interface ModalProps {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

function Modal({ title, children, onClose }: ModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-[#13131f] border border-white/[0.08] rounded-2xl p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-[17px] font-bold text-white">{title}</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-white/40 hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function RepoCard({
  repo,
  onDelete,
}: {
  repo: Repository;
  onDelete: (id: number, name: string) => void;
}) {
  const reviewsCount = repo.reviewsCount ?? repo.reviews_count ?? 0;
  const openIssues = repo.openIssues ?? repo.open_issues ?? 0;
  const successRate = repo.successRate ?? repo.success_rate ?? 100;

  return (
    <GlassCard className="hover:border-violet-500/20 transition-all duration-300 group metric-card">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
        {/* Left: repo info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2 flex-wrap">
            <div className="flex items-center gap-2 p-2 rounded-xl bg-white/[0.04] border border-white/[0.06]">
              {repo.provider === "github" ? (
                <GitBranch className="h-4 w-4 text-white/60" />
              ) : (
                <Code2 className="h-4 w-4 text-white/60" />
              )}
            </div>
            <h3 className="text-[15px] font-bold text-white group-hover:text-violet-300 transition-colors truncate">
              {repo.full_name}
            </h3>
            {repo.is_active && (
              <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[11px] font-bold text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Active
              </span>
            )}
          </div>

          <div className="flex items-center gap-4 text-[12px] text-white/30 mb-5">
            <span className="flex items-center gap-1">
              <GitBranch className="h-3 w-3" />
              {repo.default_branch}
            </span>
            <span>·</span>
            <span>
              {repo.provider.charAt(0).toUpperCase() + repo.provider.slice(1)}
            </span>
            <span>·</span>
            <span>
              {new Date(repo.created_at).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-8">
            <div>
              <p className="text-[20px] font-bold text-white leading-none">{reviewsCount}</p>
              <p className="text-[10px] text-white/35 uppercase tracking-wider font-medium mt-1">
                Reviews
              </p>
            </div>
            <div>
              <p className={`text-[20px] font-bold leading-none ${openIssues > 0 ? "text-amber-400" : "text-white"}`}>
                {openIssues}
              </p>
              <p className="text-[10px] text-white/35 uppercase tracking-wider font-medium mt-1">
                Open Issues
              </p>
            </div>
            <div>
              <p className="text-[20px] font-bold text-white leading-none">{successRate}%</p>
              <p className="text-[10px] text-white/35 uppercase tracking-wider font-medium mt-1">
                Success Rate
              </p>
            </div>
          </div>
        </div>

        {/* Right: sparkline + actions */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="opacity-60 hidden md:block">
            <Sparkline color={openIssues > 0 ? "#f97316" : "#a855f7"} />
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onDelete(repo.id, repo.full_name)}
              className="p-2 rounded-xl text-white/30 hover:text-rose-400 hover:bg-rose-500/10 transition-all duration-200"
              title="Deactivate"
            >
              <Settings className="h-4 w-4" />
            </button>
            <a
              href={`https://${repo.provider}.com/${repo.full_name}`}
              target="_blank"
              rel="noreferrer"
            >
              <button className="p-2 rounded-xl text-white/30 hover:text-white hover:bg-white/[0.06] transition-all duration-200">
                <ExternalLink className="h-4 w-4" />
              </button>
            </a>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

export default function RepositoriesPage() {
  const { repositories, loadingRepositories, fetchRepositories, addRepository, removeRepository } =
    useDashboardStore();

  const [isOpen, setIsOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [provider, setProvider] = useState<"github" | "gitlab">("github");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [deleteRepoId, setDeleteRepoId] = useState<number | null>(null);
  const [deleteRepoName, setDeleteRepoName] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      await addRepository({ provider, full_name: fullName, default_branch: defaultBranch });
      setToast({ type: "success", message: `Connected ${fullName} successfully!` });
      setIsOpen(false);
      setFullName("");
      setDefaultBranch("main");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (deleteRepoId === null) return;
    setDeleting(true);
    try {
      await removeRepository(deleteRepoId);
      setToast({ type: "success", message: `Deactivated ${deleteRepoName}!` });
      setDeleteRepoId(null);
      setDeleteRepoName("");
    } catch (err) {
      setToast({ type: "error", message: err instanceof Error ? err.message : "Failed to deactivate" });
    } finally {
      setDeleting(false);
    }
  };

  const inputCls =
    "w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-[13px] text-white placeholder:text-white/25 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30 transition-all duration-200";

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PageHeader
        title="Repositories"
        subtitle="Manage and monitor your connected code repositories."
        action={
          <button
            onClick={() => setIsOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 px-5 py-2.5 text-[13px] font-bold text-white transition-all duration-200 shadow-lg shadow-violet-600/25"
          >
            <Plus className="h-4 w-4" />
            Add Repository
          </button>
        }
      />

      {loadingRepositories ? (
        <div className="flex items-center justify-center h-48">
          <LoadingSpinner />
        </div>
      ) : repositories.length === 0 ? (
        <GlassCard className="flex flex-col items-center justify-center py-20 text-center">
          <div className="h-20 w-20 rounded-3xl bg-white/[0.04] border border-white/[0.07] flex items-center justify-center mb-6">
            <Layers className="h-10 w-10 text-white/20" />
          </div>
          <h3 className="text-[20px] font-bold text-white mb-2">No repositories connected</h3>
          <p className="text-white/40 max-w-sm mb-8 text-[14px] leading-relaxed">
            Connect your GitHub or GitLab repositories to start getting automated AI-powered PR reviews.
          </p>
          <button
            onClick={() => { setProvider("github"); setIsOpen(true); }}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 px-6 py-3 text-[13px] font-bold text-white transition-all duration-200 shadow-lg shadow-violet-600/25"
          >
            <GitBranch className="h-4 w-4" />
            Connect GitHub
          </button>
        </GlassCard>
      ) : (
        <div className="grid gap-5">
          {repositories.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              onDelete={(id, name) => { setDeleteRepoId(id); setDeleteRepoName(name); }}
            />
          ))}
        </div>
      )}

      {/* Add Repository Modal */}
      {isOpen && (
        <Modal title="Connect Repository" onClose={() => { setIsOpen(false); setFormError(null); }}>
          <form onSubmit={handleSubmit} className="space-y-5">
            {formError && (
              <div className="flex items-center gap-2 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-[13px] text-rose-400 font-medium">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {formError}
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Provider
              </label>
              <div className="grid grid-cols-2 gap-3">
                {(["github", "gitlab"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setProvider(p)}
                    className={`flex items-center justify-center gap-2 py-3 px-3 rounded-xl border text-[13px] font-semibold transition-all duration-200 ${
                      provider === p
                        ? "bg-violet-600/15 border-violet-500/40 text-violet-300"
                        : "bg-white/[0.03] border-white/[0.07] text-white/50 hover:text-white/70 hover:bg-white/[0.05]"
                    }`}
                  >
                    {p === "github" ? <GitBranch className="h-4 w-4" /> : <Code2 className="h-4 w-4" />}
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Repository Name
              </label>
              <input
                type="text"
                required
                placeholder="e.g. owner/repo"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className={inputCls}
              />
            </div>

            <div className="space-y-2">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Default Branch
              </label>
              <input
                type="text"
                required
                placeholder="e.g. main"
                value={defaultBranch}
                onChange={(e) => setDefaultBranch(e.target.value)}
                className={inputCls}
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => { setIsOpen(false); setFormError(null); }}
                disabled={submitting}
                className="px-4 py-2.5 rounded-xl text-[13px] font-semibold text-white/50 hover:text-white/70 hover:bg-white/[0.05] transition-all duration-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-[13px] font-bold text-white transition-all duration-200 shadow-lg shadow-violet-600/20 disabled:opacity-60"
              >
                {submitting ? (
                  <>
                    <LoadingSpinner size="sm" /> Connecting...
                  </>
                ) : (
                  "Connect Repository"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Deactivate Confirmation Modal */}
      {deleteRepoId !== null && (
        <Modal title="Deactivate Repository" onClose={() => { setDeleteRepoId(null); setDeleteRepoName(""); }}>
          <div className="flex items-start gap-4 mb-6">
            <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 shrink-0">
              <ShieldAlert className="h-6 w-6 text-rose-400" />
            </div>
            <div>
              <p className="text-[14px] text-white/70 leading-relaxed">
                Are you sure you want to deactivate{" "}
                <span className="font-bold text-white">{deleteRepoName}</span>? It will no longer receive automated code reviews.
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => { setDeleteRepoId(null); setDeleteRepoName(""); }}
              disabled={deleting}
              className="px-4 py-2.5 rounded-xl text-[13px] font-semibold text-white/50 hover:text-white/70 hover:bg-white/[0.05] transition-all duration-200"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-rose-500 hover:bg-rose-600 text-[13px] font-bold text-white transition-all duration-200 shadow-lg shadow-rose-500/20 disabled:opacity-60"
            >
              {deleting ? (
                <>
                  <LoadingSpinner size="sm" /> Deactivating...
                </>
              ) : (
                "Deactivate"
              )}
            </button>
          </div>
        </Modal>
      )}

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl border shadow-2xl animate-in slide-in-from-bottom-4 duration-300 backdrop-blur-md ${
            toast.type === "success"
              ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-400"
              : "bg-rose-500/10 border-rose-500/25 text-rose-400"
          }`}
        >
          {toast.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0" />
          )}
          <span className="text-[13px] font-semibold">{toast.message}</span>
        </div>
      )}
    </div>
  );
}
