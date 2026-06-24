"use client";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Layers, Plus, ExternalLink, Settings, GitBranch, Code2 } from "lucide-react";
import { readJson } from "@/lib/api";

interface Repository {
  id: number;
  provider: string;
  full_name: string;
  default_branch: string;
  is_active: boolean;
  created_at: string;
}

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal & form states
  const [isOpen, setIsOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [provider, setProvider] = useState<"github" | "gitlab">("github");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Deactivate modal states
  const [deleteRepoId, setDeleteRepoId] = useState<number | null>(null);
  const [deleteRepoName, setDeleteRepoName] = useState<string>("");
  const [deleting, setDeleting] = useState(false);

  const getErrorMessage = (err: unknown, fallback: string) => {
    return err instanceof Error ? err.message : fallback;
  };

  const fetchRepos = (showLoading = true) => {
    if (showLoading) {
      setLoading(true);
    }

    fetch("/api/v3/repositories")
      .then(res => readJson<Repository[]>(res))
      .then(data => {
        setRepos(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetch("/api/v3/repositories")
      .then(res => readJson<Repository[]>(res))
      .then(data => {
        setRepos(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/v3/repositories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          provider,
          full_name: fullName,
          default_branch: defaultBranch,
        }),
      });

      await readJson<unknown>(response);

      setToast({ type: "success", message: `Successfully connected ${fullName}!` });
      setIsOpen(false);
      setFullName("");
      setDefaultBranch("main");
      fetchRepos();
    } catch (err: unknown) {
      setError(getErrorMessage(err, "An unexpected error occurred"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (deleteRepoId === null) return;
    setDeleting(true);
    try {
      const response = await fetch(`/api/v3/repositories/${deleteRepoId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to deactivate repository");
      }

      setToast({ type: "success", message: `Successfully deactivated ${deleteRepoName}!` });
      setDeleteRepoId(null);
      setDeleteRepoName("");
      fetchRepos();
    } catch (err: unknown) {
      setToast({ type: "error", message: getErrorMessage(err, "An unexpected error occurred") });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Repositories</h1>
          <p className="text-zinc-400 mt-1">Manage repositories connected to DevAssist-AI.</p>
        </div>
        <Button 
          onClick={() => setIsOpen(true)}
          className="bg-orange-600 hover:bg-orange-700 text-white shadow-lg shadow-orange-900/20"
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Repository
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
        </div>
      ) : repos.length === 0 ? (
        <Card className="bg-zinc-900/30 border-zinc-800/60 p-12 flex flex-col items-center justify-center text-center">
          <div className="h-16 w-16 rounded-full bg-zinc-800/50 flex items-center justify-center mb-6">
            <Layers className="h-8 w-8 text-zinc-500" />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">No repositories connected</h3>
          <p className="text-zinc-400 max-w-md mb-8">
            Connect your GitHub or GitLab repositories to start getting automated PR reviews.
          </p>
          <Button 
            onClick={() => { setProvider("github"); setIsOpen(true); }}
            className="bg-zinc-100 text-zinc-900 hover:bg-white"
          >
            <GitBranch className="mr-2 h-4 w-4" />
            Connect GitHub
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4">
          {repos.map((repo) => (
            <Card key={repo.id} className="bg-zinc-900/50 border-zinc-800 p-6 flex items-center justify-between hover:border-zinc-700 transition-colors group">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-zinc-800/80 rounded-xl text-zinc-300">
                  {repo.provider === "github" ? <GitBranch className="h-6 w-6" /> : <Code2 className="h-6 w-6" />}
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    {repo.full_name}
                    {repo.is_active && (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-medium text-emerald-400 uppercase tracking-wider">
                        Active
                      </span>
                    )}
                  </h3>
                  <div className="flex items-center gap-4 mt-1 text-sm text-zinc-500">
                    <span className="flex items-center gap-1">
                      <GitBranch className="h-3.5 w-3.5" />
                      {repo.default_branch}
                    </span>
                    <span>Added {new Date(repo.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                <Button
                  onClick={() => {
                    setDeleteRepoId(repo.id);
                    setDeleteRepoName(repo.full_name);
                  }}
                  variant="ghost"
                  size="icon"
                  className="text-zinc-400 hover:text-white hover:bg-zinc-800"
                >
                  <Settings className="h-4 w-4" />
                </Button>
                <a href={`https://${repo.provider}.com/${repo.full_name}`} target="_blank" rel="noreferrer">
                  <Button variant="ghost" size="icon" className="text-zinc-400 hover:text-white hover:bg-zinc-800">
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </a>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Connect Repository Modal Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-2xl space-y-4 text-white">
            <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <GitBranch className="h-5 w-5 text-orange-500" />
              Connect Repository
            </h2>
            <p className="text-zinc-400 text-sm">
              Enter details below to monitor and review pull requests.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 bg-red-950/40 border border-red-500/30 rounded-lg text-sm text-red-400">
                  {error}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Provider</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setProvider("github")}
                    className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg border text-sm font-medium transition-colors ${
                      provider === "github"
                        ? "bg-zinc-800 border-orange-500/50 text-white"
                        : "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-white"
                    }`}
                  >
                    <GitBranch className="h-4 w-4" />
                    GitHub
                  </button>
                  <button
                    type="button"
                    onClick={() => setProvider("gitlab")}
                    className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg border text-sm font-medium transition-colors ${
                      provider === "gitlab"
                        ? "bg-zinc-800 border-orange-500/50 text-white"
                        : "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-white"
                    }`}
                  >
                    <Code2 className="h-4 w-4" />
                    GitLab
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Repository Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. owner/repo"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-orange-500 transition-colors"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Default Branch</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. main"
                  value={defaultBranch}
                  onChange={(e) => setDefaultBranch(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-orange-500 transition-colors"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setIsOpen(false);
                    setError(null);
                  }}
                  disabled={submitting}
                  className="text-zinc-400 hover:text-white hover:bg-zinc-800"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={submitting}
                  className="bg-orange-600 hover:bg-orange-700 text-white shadow-lg"
                >
                  {submitting ? "Validating & Connecting..." : "Connect"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteRepoId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-2xl space-y-4 text-white">
            <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              Deactivate Repository
            </h2>
            <p className="text-zinc-400 text-sm">
              Are you sure you want to deactivate <span className="font-semibold text-white">{deleteRepoName}</span>? It will no longer receive automated code reviews.
            </p>

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDeleteRepoId(null);
                  setDeleteRepoName("");
                }}
                disabled={deleting}
                className="text-zinc-400 hover:text-white hover:bg-zinc-800"
              >
                Cancel
              </Button>
              <Button
                onClick={handleDelete}
                disabled={deleting}
                className="bg-red-600 hover:bg-red-700 text-white shadow-lg"
              >
                {deleting ? "Deactivating..." : "Deactivate"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg border shadow-xl animate-in slide-in-from-bottom-2 duration-300 ${
          toast.type === "success" 
            ? "bg-emerald-950/90 border-emerald-500/30 text-emerald-400" 
            : "bg-red-950/90 border-red-500/30 text-red-400"
        }`}>
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}
