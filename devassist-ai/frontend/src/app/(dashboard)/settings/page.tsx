"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Settings,
  Webhook,
  Key,
  Server,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Eye,
  EyeOff,
  ExternalLink,
  RefreshCw,
  GitBranch,
  Cpu,
  Database,
  Zap,
  FlaskConical,
  Loader2,
  Bell,
  Shield,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
} from "lucide-react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useDashboardStore, PipelineSettings } from "@/lib/stores/dashboardStore";
import { GlassCard, LoadingSpinner, PageHeader } from "@/components/ui/shared";
import { apiFetch } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────
interface SystemStatus {
  status: string;
  database: boolean;
  llm_provider: string;
  llm_model: string;
  version: string;
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function Toast({ msg, type }: { msg: string; type: "success" | "error" }) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl border shadow-2xl animate-in slide-in-from-bottom-4 duration-300 backdrop-blur-md ${
        type === "success"
          ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-400"
          : "bg-rose-500/10 border-rose-500/25 text-rose-400"
      }`}
    >
      {type === "success" ? (
        <CheckCircle2 className="h-5 w-5 shrink-0" />
      ) : (
        <AlertTriangle className="h-5 w-5 shrink-0" />
      )}
      <span className="text-[13px] font-semibold">{msg}</span>
    </div>
  );
}

function SettingItem({ label, value, secret }: { label: string; value: string; secret?: boolean }) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);

  const display = secret && !revealed ? "••••••••••••••••" : value || "Not configured";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center justify-between py-4 border-b border-white/[0.05] last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-white/80">{label}</p>
        <p
          className={`text-[13px] mt-0.5 font-mono ${
            secret && !revealed ? "text-white/20 tracking-widest" : "text-white/40"
          }`}
        >
          {display}
        </p>
      </div>
      <div className="flex items-center gap-1 ml-4 shrink-0">
        {secret && (
          <button
            onClick={() => setRevealed((v) => !v)}
            className="p-2 rounded-xl text-white/30 hover:text-white/70 hover:bg-white/[0.06] transition-all duration-200"
          >
            {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
        {value && (
          <button
            onClick={handleCopy}
            className="p-2 rounded-xl text-white/30 hover:text-white/70 hover:bg-white/[0.06] transition-all duration-200"
          >
            {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
          </button>
        )}
      </div>
    </div>
  );
}

function SectionCard({ title, icon: Icon, children, accent = "violet" }: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  accent?: "violet" | "cyan" | "emerald" | "rose";
}) {
  const accentMap: Record<string, string> = {
    violet: "text-violet-400 bg-violet-500/10 border-violet-500/20",
    cyan: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    rose: "text-rose-400 bg-rose-500/10 border-rose-500/20",
  };
  return (
    <GlassCard>
      <div className="flex items-center gap-3 mb-5 pb-4 border-b border-white/[0.05]">
        <div className={`p-2 rounded-xl border ${accentMap[accent]}`}>
          <Icon className="h-4 w-4" />
        </div>
        <h3 className="text-[15px] font-bold text-white">{title}</h3>
      </div>
      {children}
    </GlassCard>
  );
}

function ReviewModeCard({
  mode, emoji, title, description, detail, active, loading, onClick,
}: {
  mode: string; emoji: string; title: string; description: string; detail: string;
  active: boolean; loading: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`group relative flex-1 min-w-[240px] rounded-2xl border-2 p-6 text-left transition-all duration-300 ${
        active
          ? "border-emerald-500/50 bg-emerald-500/[0.05] shadow-[0_0_30px_-8px_rgba(16,185,129,0.15)]"
          : "border-white/[0.07] bg-white/[0.02] hover:border-violet-500/30 hover:bg-white/[0.04]"
      } ${loading ? "opacity-60 cursor-wait" : "cursor-pointer"}`}
    >
      {active && (
        <div className="absolute top-4 right-4 flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Active</span>
        </div>
      )}

      <div
        className={`h-12 w-12 rounded-xl flex items-center justify-center text-xl mb-4 border transition-all duration-300 ${
          active ? "bg-emerald-500/10 border-emerald-500/20" : "bg-white/[0.04] border-white/[0.07] group-hover:border-violet-500/20"
        }`}
      >
        <span className="text-2xl drop-shadow-sm" role="img">{emoji}</span>
      </div>

      <h4 className={`text-[16px] font-bold mb-2 transition-colors ${active ? "text-emerald-400" : "text-white group-hover:text-violet-300"}`}>
        {title}
      </h4>
      <p className={`text-[13px] leading-relaxed mb-3 ${active ? "text-emerald-400/60" : "text-white/45"}`}>
        {description}
      </p>
      <p className="text-[11px] font-mono text-white/25">{detail}</p>

      {loading && (
        <div className="absolute inset-0 rounded-2xl flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <Loader2 className="h-6 w-6 text-emerald-400 animate-spin" />
        </div>
      )}
    </button>
  );
}

// Simple toggle component
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-300 ${
        checked ? "bg-violet-600" : "bg-white/10"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transform transition-transform duration-300 ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

type TabKey = "system" | "pipeline" | "integrations" | "api";

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "system", label: "System", icon: Server },
  { key: "pipeline", label: "Pipeline", icon: FlaskConical },
  { key: "integrations", label: "Webhooks", icon: Webhook },
  { key: "api", label: "API & Tokens", icon: Key },
];

// ── Page ───────────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { pipelineSettings, fetchPipelineSettings, setReviewMode } = useDashboardStore();
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [modeLoading, setModeLoading] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("system");
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // Notification toggles (UI only, would persist via settings API)
  const [emailNotif, setEmailNotif] = useState(true);
  const [inAppAlerts, setInAppAlerts] = useState(true);
  const [pushNotif, setPushNotif] = useState(false);
  const [summaryFreq, setSummaryFreq] = useState("Weekly");

  const showToast = useCallback((msg: string, type: "success" | "error") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const fetchStatus = async () => {
    setRefreshing(true);
    try {
      const data = await apiFetch<SystemStatus>("/api/v3/status");
      setSystemStatus(data);
    } catch {
      setSystemStatus(null);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchPipelineSettings();
  }, [fetchPipelineSettings]);

  const handleSetMode = async (mode: string) => {
    if (pipelineSettings?.review_mode === mode) return;
    setModeLoading(mode);
    try {
      await setReviewMode(mode);
      showToast(`Switched to ${mode === "fast" ? "Fast ⚡" : "Ensemble 🔬"} mode`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to update mode", "error");
    } finally {
      setModeLoading(null);
    }
  };

  // Dummy quality score sparkline
  const qualityData = Array.from({ length: 14 }, (_, i) => ({
    v: 60 + Math.sin(i * 0.8) * 20 + Math.random() * 10,
  }));

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {toast && <Toast msg={toast.msg} type={toast.type} />}

      <PageHeader
        title="Settings"
        subtitle="Manage your DevAssist AI configuration and integrations."
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/[0.07] w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-[13px] font-semibold transition-all duration-200 ${
              activeTab === tab.key
                ? "bg-violet-600/20 text-violet-300 border border-violet-500/30"
                : "text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── System Tab ──────────────────────────────────────────────────────── */}
      {activeTab === "system" && (
        <div className="space-y-6">
          {/* Status banner */}
          <GlassCard className="overflow-hidden relative">
            <div className="absolute right-0 top-0 w-64 h-64 bg-violet-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
            <div className="relative flex items-center justify-between">
              <div className="flex items-center gap-5">
                <div
                  className={`h-14 w-14 rounded-2xl flex items-center justify-center border-2 ${
                    systemStatus?.database
                      ? "border-emerald-500/30 bg-emerald-500/10 shadow-[0_0_20px_-4px_rgba(16,185,129,0.25)]"
                      : "border-amber-500/30 bg-amber-500/10"
                  }`}
                >
                  <Database
                    className={`h-6 w-6 ${systemStatus?.database ? "text-emerald-400" : "text-amber-400"}`}
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="text-[17px] font-bold text-white">Backend Status</h2>
                    {systemStatus?.database && (
                      <span className="relative flex h-2 w-2 ml-1">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                    )}
                  </div>
                  <p className="text-[14px] text-white/40 font-medium">
                    {systemStatus
                      ? systemStatus.database
                        ? `PostgreSQL connected · v${systemStatus.version}`
                        : "Database unreachable — check your connection"
                      : "Fetching status…"}
                  </p>
                </div>
              </div>
              <button
                onClick={fetchStatus}
                disabled={refreshing}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.08] text-[13px] font-semibold text-white/60 hover:text-white hover:bg-white/[0.07] transition-all duration-200 disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>
          </GlassCard>

          {/* Two-column layout matching design */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Account Profile */}
            <SectionCard title="AI / LLM Configuration" icon={Cpu} accent="violet">
              <SettingItem label="LLM Provider" value={systemStatus?.llm_provider ?? ""} />
              <SettingItem label="Active Model" value={systemStatus?.llm_model ?? ""} />
              <SettingItem label="API Version" value={systemStatus?.version ?? ""} />
              <SettingItem label="Database Status" value={systemStatus?.database ? "Connected" : "Disconnected"} />
            </SectionCard>

            {/* Notification Preferences */}
            <SectionCard title="Notification Preferences" icon={Bell} accent="cyan">
              <div className="space-y-4">
                {[
                  { label: "Email Notifications", value: emailNotif, onChange: setEmailNotif, icon: "📧" },
                  { label: "In-App Alerts", value: inAppAlerts, onChange: setInAppAlerts, icon: "🔔" },
                  { label: "Push Notifications", value: pushNotif, onChange: setPushNotif, icon: "📱" },
                ].map((item) => (
                  <div key={item.label} className="flex items-center justify-between py-3 border-b border-white/[0.05] last:border-0">
                    <div className="flex items-center gap-3">
                      <span>{item.icon}</span>
                      <p className="text-[13px] font-semibold text-white/70">{item.label}</p>
                    </div>
                    <Toggle checked={item.value} onChange={item.onChange} />
                  </div>
                ))}
                <div className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <span>📋</span>
                    <p className="text-[13px] font-semibold text-white/70">Summary Reports</p>
                  </div>
                  <div className="relative">
                    <select
                      value={summaryFreq}
                      onChange={(e) => setSummaryFreq(e.target.value)}
                      className="appearance-none bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2 pr-8 text-[12px] font-medium text-white/70 focus:outline-none focus:border-violet-500/40 cursor-pointer"
                    >
                      <option value="Daily">Daily</option>
                      <option value="Weekly">Weekly</option>
                      <option value="Monthly">Monthly</option>
                    </select>
                    <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30 pointer-events-none" />
                  </div>
                </div>
              </div>
            </SectionCard>
          </div>

          {/* Info alert */}
          <div className="flex items-start gap-3 p-4 rounded-2xl bg-amber-500/5 border border-amber-500/15">
            <Settings className="h-4 w-4 text-amber-400/70 shrink-0 mt-0.5" />
            <p className="text-[13px] text-amber-400/60 font-medium leading-relaxed">
              Backend configuration is managed through environment variables or the{" "}
              <code className="text-amber-300 font-bold bg-amber-500/10 px-1.5 py-0.5 rounded">.env</code>{" "}
              file. Restart the API service after making changes.
            </p>
          </div>
        </div>
      )}

      {/* ── Pipeline Tab ────────────────────────────────────────────────────── */}
      {activeTab === "pipeline" && (
        <div className="space-y-6">
          {/* Header card */}
          <GlassCard className="overflow-hidden relative">
            <div className="absolute right-0 top-0 w-48 h-48 bg-emerald-500/5 rounded-full blur-3xl -mr-12 -mt-12 pointer-events-none" />
            <div className="relative flex items-center gap-4">
              <div className="h-14 w-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <FlaskConical className="h-7 w-7 text-emerald-400" />
              </div>
              <div>
                <h2 className="text-[17px] font-bold text-white">Review Pipeline</h2>
                <p className="text-[14px] text-white/40 mt-0.5">Choose how DevAssist AI analyses your pull requests.</p>
              </div>
            </div>
          </GlassCard>

          {/* Mode selector */}
          <div className="flex flex-col sm:flex-row gap-5">
            <ReviewModeCard
              mode="fast"
              emoji="⚡"
              title="Fast Mode"
              description="Single-model review. Quick, reliable, and efficient for most PRs."
              detail="1 LLM call · ~15s per file"
              active={pipelineSettings?.review_mode === "fast"}
              loading={modeLoading === "fast"}
              onClick={() => handleSetMode("fast")}
            />
            <ReviewModeCard
              mode="ensemble"
              emoji="🔬"
              title="Ensemble Mode"
              description="Three-stage pipeline: Distill → Reason → Validate. More thorough but slower."
              detail="3 LLM calls · ~45s per file"
              active={pipelineSettings?.review_mode === "ensemble"}
              loading={modeLoading === "ensemble"}
              onClick={() => handleSetMode("ensemble")}
            />
          </div>

          {/* Pipeline settings + Quality sparkline */}
          {pipelineSettings && (
            <div className="grid gap-6 lg:grid-cols-2">
              <SectionCard title="Current Pipeline Settings" icon={Cpu} accent="violet">
                <SettingItem label="Review Mode" value={pipelineSettings.review_mode} />
                <SettingItem label="LLM Model" value={pipelineSettings.llm_model} />
                <SettingItem label="LLM Provider" value={pipelineSettings.llm_provider} />
                <SettingItem label="RAG Enabled" value={pipelineSettings.rag_enabled ? "Yes" : "No"} />
              </SectionCard>

              {/* Code Quality Sparkline */}
              <GlassCard>
                <h3 className="text-[15px] font-bold text-white mb-1">Code Quality Score</h3>
                <p className="text-[12px] text-white/40 mb-5">Last 14 days trend</p>
                <div className="h-28">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={qualityData}>
                      <defs>
                        <linearGradient id="qgrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#a855f7" stopOpacity={0.25} />
                          <stop offset="100%" stopColor="#a855f7" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="v" stroke="#a855f7" strokeWidth={2} fill="url(#qgrad)" dot={false} />
                      <Tooltip
                        contentStyle={{
                          background: "#13131f",
                          border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: "10px",
                          fontSize: "12px",
                          color: "#fff",
                        }}
                        formatter={(v) => [`${v != null ? Math.round(Number(v)) : 0}%`, "Score"]}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </GlassCard>
            </div>
          )}

          <div className="flex items-start gap-3 p-4 rounded-2xl bg-violet-500/5 border border-violet-500/15">
            <Zap className="h-4 w-4 text-violet-400/70 shrink-0 mt-0.5" />
            <p className="text-[13px] text-violet-400/60 font-medium leading-relaxed">
              Pipeline mode changes take effect immediately for new reviews. For permanent changes, update the{" "}
              <code className="text-violet-300 font-bold bg-violet-500/10 px-1.5 py-0.5 rounded">REVIEW_MODE</code>{" "}
              environment variable.
            </p>
          </div>
        </div>
      )}

      {/* ── Webhooks Tab ────────────────────────────────────────────────────── */}
      {activeTab === "integrations" && (
        <div className="space-y-6">
          {[
            {
              title: "GitHub Webhooks",
              desc: "Configure GitHub to send webhook events to your DevAssist AI instance.",
              endpoint: "https://<your-domain>/api/v3/github/webhook",
              items: [
                { label: "Content type", value: "application/json" },
                { label: "Events", value: "Pull requests" },
                { label: "Secret", value: "Set via GITHUB_WEBHOOK_SECRET env var" },
              ],
              docs: "https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks",
            },
            {
              title: "GitLab Webhooks",
              desc: "Configure GitLab to send merge request events to DevAssist AI.",
              endpoint: "https://<your-domain>/api/v3/gitlab/webhook",
              items: [
                { label: "Events", value: "Merge Request Events" },
                { label: "Secret Token", value: "Set via GITLAB_WEBHOOK_SECRET env var" },
              ],
              docs: "https://docs.gitlab.com/ee/user/project/integrations/webhooks.html",
            },
          ].map((wh) => (
            <SectionCard key={wh.title} title={wh.title} icon={GitBranch} accent="cyan">
              <p className="text-[13px] text-white/40 mb-5 leading-relaxed">{wh.desc}</p>
              <div className="rounded-xl bg-white/[0.03] border border-white/[0.07] p-4 font-mono text-[13px] flex items-center justify-between gap-3 mb-5">
                <code className="text-violet-400 font-bold truncate">{wh.endpoint}</code>
                <button
                  onClick={() => navigator.clipboard.writeText(wh.endpoint)}
                  className="p-2 rounded-xl text-white/30 hover:text-white/70 hover:bg-white/[0.06] transition-all shrink-0"
                >
                  <Copy className="h-4 w-4" />
                </button>
              </div>
              <ul className="space-y-3 mb-5">
                {wh.items.map((row) => (
                  <li key={row.label} className="flex items-center gap-3 text-[13px]">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    <span className="text-white/40 font-semibold">{row.label}:</span>
                    <span className="text-white/70">{row.value}</span>
                  </li>
                ))}
              </ul>
              <a
                href={wh.docs}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-[13px] font-bold text-violet-400 hover:text-violet-300 transition-colors"
              >
                View docs <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </SectionCard>
          ))}
        </div>
      )}

      {/* ── API & Tokens Tab ─────────────────────────────────────────────────── */}
      {activeTab === "api" && (
        <div className="space-y-6">
          <div className="flex items-start gap-3 p-4 rounded-2xl bg-amber-500/5 border border-amber-500/15">
            <AlertTriangle className="h-4 w-4 text-amber-400/70 shrink-0 mt-0.5" />
            <p className="text-[13px] text-amber-400/60 font-medium leading-relaxed">
              Tokens are read-only and loaded from server environment variables. To update them, edit your{" "}
              <code className="font-bold bg-amber-500/10 px-1.5 py-0.5 rounded text-amber-400">.env</code>{" "}
              file and restart the API.
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Provider Tokens" icon={Key} accent="violet">
              <SettingItem label="GitHub Personal Access Token" value="Configured via GITHUB_TOKEN" secret />
              <SettingItem label="GitLab Token" value="Configured via GITLAB_TOKEN" secret />
              <SettingItem label="GitHub Webhook Secret" value="Configured via GITHUB_WEBHOOK_SECRET" secret />
              <SettingItem label="GitLab Webhook Secret" value="Configured via GITLAB_WEBHOOK_SECRET" secret />
            </SectionCard>

            <SectionCard title="LLM API Keys" icon={Cpu} accent="cyan">
              <SettingItem label="Google Gemini API Key" value="Configured via GEMINI_API_KEY" secret />
              <SettingItem label="OpenAI API Key" value="Configured via OPENAI_API_KEY" secret />

              {/* FastAPI docs links */}
              <div className="pt-5 mt-5 border-t border-white/[0.05]">
                <p className="text-[13px] font-bold text-white mb-3">API Documentation</p>
                <div className="flex gap-3 flex-wrap">
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl bg-white/[0.04] border border-white/[0.08] px-4 py-2.5 text-[12px] font-bold text-white/70 hover:text-white hover:border-violet-500/30 hover:bg-white/[0.07] transition-all"
                  >
                    Swagger UI <ExternalLink className="h-3.5 w-3.5 text-white/30" />
                  </a>
                  <a
                    href="/api/redoc"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl bg-white/[0.04] border border-white/[0.08] px-4 py-2.5 text-[12px] font-bold text-white/70 hover:text-white hover:border-violet-500/30 hover:bg-white/[0.07] transition-all"
                  >
                    ReDoc <ExternalLink className="h-3.5 w-3.5 text-white/30" />
                  </a>
                </div>
              </div>
            </SectionCard>
          </div>
        </div>
      )}
    </div>
  );
}
