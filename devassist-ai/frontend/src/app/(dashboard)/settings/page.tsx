"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
} from "lucide-react";
import { readJson } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SystemStatus {
  status: string;
  database: boolean;
  llm_provider: string;
  llm_model: string;
  version: string;
}

interface SettingRow {
  label: string;
  value: string;
  secret?: boolean;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SettingItem({ label, value, secret }: SettingRow) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);

  const display = secret && !revealed ? "••••••••••••••••" : value || "Not configured";
  const isMasked = secret && !revealed;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center justify-between py-3 border-b border-zinc-800/60 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-300">{label}</p>
        <p
          className={`text-sm mt-0.5 font-mono ${
            isMasked ? "text-zinc-600 tracking-widest" : "text-zinc-400"
          }`}
        >
          {display}
        </p>
      </div>
      <div className="flex items-center gap-2 ml-4 shrink-0">
        {secret && (
          <button
            onClick={() => setRevealed((v) => !v)}
            className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            title={revealed ? "Hide" : "Reveal"}
          >
            {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        )}
        {value && (
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            title="Copy"
          >
            {copied ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function SectionCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800 p-6">
      <div className="flex items-center gap-2 mb-5">
        <Icon className="h-4 w-4 text-orange-500" />
        <h3 className="text-base font-semibold text-zinc-200">{title}</h3>
      </div>
      {children}
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/v3/status");
      const data = await readJson<SystemStatus>(res);
      setSystemStatus(data);
    } catch {
      setSystemStatus(null);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <div className="mx-auto max-w-4xl p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight">Settings</h1>
        <p className="text-zinc-400 mt-1">
          Manage your DevAssist-AI configuration and integrations.
        </p>
      </div>

      <Tabs defaultValue="system" className="space-y-6">
        <TabsList className="bg-zinc-900/50 border border-zinc-800 p-1 rounded-md">
          <TabsTrigger
            value="system"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400"
          >
            <Server className="mr-2 h-4 w-4" />
            System
          </TabsTrigger>
          <TabsTrigger
            value="integrations"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400"
          >
            <Webhook className="mr-2 h-4 w-4" />
            Webhooks & Integrations
          </TabsTrigger>
          <TabsTrigger
            value="api"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-white text-zinc-400"
          >
            <Key className="mr-2 h-4 w-4" />
            API & Tokens
          </TabsTrigger>
        </TabsList>

        {/* ── System Tab ────────────────────────────────────────── */}
        <TabsContent value="system" className="space-y-6">
          {/* Status banner */}
          <Card className="bg-gradient-to-r from-zinc-900/80 to-zinc-900/40 border-zinc-800 p-6 overflow-hidden relative">
            <div className="absolute right-0 top-0 w-64 h-64 bg-orange-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
            <div className="relative z-10 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div
                  className={`h-12 w-12 rounded-full border-2 flex items-center justify-center ${
                    systemStatus?.database
                      ? "border-emerald-500/30 bg-emerald-500/10"
                      : "border-amber-500/30 bg-amber-500/10"
                  }`}
                >
                  <Database
                    className={`h-6 w-6 ${
                      systemStatus?.database ? "text-emerald-400" : "text-amber-400"
                    }`}
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-white">
                      Backend Status
                    </h2>
                    {systemStatus?.database && (
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-400 mt-0.5">
                    {systemStatus
                      ? systemStatus.database
                        ? `PostgreSQL connected · v${systemStatus.version}`
                        : "Database unreachable — check your connection"
                      : "Fetching status…"}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchStatus}
                disabled={refreshing}
                className="bg-zinc-800/50 border-zinc-700 text-zinc-300 hover:bg-zinc-700 hover:text-white"
              >
                <RefreshCw
                  className={`mr-2 h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
                />
                Refresh
              </Button>
            </div>
          </Card>

          {/* AI / LLM */}
          <SectionCard title="AI / LLM Configuration" icon={Cpu}>
            <div className="divide-y divide-zinc-800/60">
              <SettingItem
                label="LLM Provider"
                value={systemStatus?.llm_provider ?? ""}
              />
              <SettingItem
                label="Active Model"
                value={systemStatus?.llm_model ?? ""}
              />
              <SettingItem
                label="API Version"
                value={systemStatus?.version ?? ""}
              />
            </div>
          </SectionCard>

          {/* Backend env note */}
          <Alert className="bg-zinc-900/50 border-zinc-700">
            <Settings className="h-4 w-4 text-zinc-400" />
            <AlertDescription className="text-zinc-400 text-sm">
              Backend configuration is managed through environment variables or
              the <code className="text-orange-400 font-mono text-xs">.env</code>{" "}
              file. Restart the API service after making changes.
            </AlertDescription>
          </Alert>
        </TabsContent>

        {/* ── Webhooks & Integrations Tab ───────────────────────── */}
        <TabsContent value="integrations" className="space-y-6">
          <SectionCard title="GitHub Webhooks" icon={GitBranch}>
            <div className="space-y-4">
              <p className="text-sm text-zinc-400">
                Configure GitHub to send webhook events to your DevAssist-AI
                instance. Use the endpoint below in your repository or
                organisation webhook settings.
              </p>

              <div className="rounded-lg bg-zinc-800/60 border border-zinc-700/50 p-4 font-mono text-sm flex items-center justify-between gap-3">
                <code className="text-orange-400 truncate">
                  https://&lt;your-domain&gt;/api/v3/github/webhook
                </code>
                <button
                  onClick={() =>
                    navigator.clipboard.writeText(
                      "https://<your-domain>/api/v3/github/webhook"
                    )
                  }
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700 transition-colors shrink-0"
                  title="Copy"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
              </div>

              <ul className="space-y-2 text-sm text-zinc-400">
                {[
                  { label: "Content type", value: "application/json" },
                  { label: "Events", value: "Pull requests" },
                  {
                    label: "Secret",
                    value: "Set via GITHUB_WEBHOOK_SECRET env var",
                  },
                ].map((row) => (
                  <li key={row.label} className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    <span className="text-zinc-500">{row.label}:</span>
                    <span>{row.value}</span>
                  </li>
                ))}
              </ul>

              <a
                href="https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-orange-500 hover:text-orange-400 transition-colors"
              >
                GitHub webhook docs
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </SectionCard>

          <SectionCard title="GitLab Webhooks" icon={GitBranch}>
            <div className="space-y-4">
              <p className="text-sm text-zinc-400">
                Configure GitLab to send merge request events to DevAssist-AI.
              </p>
              <div className="rounded-lg bg-zinc-800/60 border border-zinc-700/50 p-4 font-mono text-sm flex items-center justify-between gap-3">
                <code className="text-orange-400 truncate">
                  https://&lt;your-domain&gt;/api/v3/gitlab/webhook
                </code>
                <button
                  onClick={() =>
                    navigator.clipboard.writeText(
                      "https://<your-domain>/api/v3/gitlab/webhook"
                    )
                  }
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700 transition-colors shrink-0"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </SectionCard>
        </TabsContent>

        {/* ── API & Tokens Tab ──────────────────────────────────── */}
        <TabsContent value="api" className="space-y-6">
          <Alert className="bg-amber-500/5 border-amber-500/20">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <AlertDescription className="text-zinc-300 text-sm">
              Tokens are read-only and loaded from server environment variables.
              To update them, edit your{" "}
              <code className="font-mono text-orange-400 text-xs">.env</code>{" "}
              file and restart the API.
            </AlertDescription>
          </Alert>

          <SectionCard title="Provider Tokens" icon={Key}>
            <div className="divide-y divide-zinc-800/60">
              <SettingItem
                label="GitHub Personal Access Token"
                value="Configured via GITHUB_TOKEN"
                secret
              />
              <SettingItem
                label="GitLab Token"
                value="Configured via GITLAB_TOKEN"
                secret
              />
              <SettingItem
                label="GitHub Webhook Secret"
                value="Configured via GITHUB_WEBHOOK_SECRET"
                secret
              />
              <SettingItem
                label="GitLab Webhook Secret"
                value="Configured via GITLAB_WEBHOOK_SECRET"
                secret
              />
            </div>
          </SectionCard>

          <SectionCard title="LLM API Keys" icon={Cpu}>
            <div className="divide-y divide-zinc-800/60">
              <SettingItem
                label="Google Gemini API Key"
                value="Configured via GEMINI_API_KEY"
                secret
              />
              <SettingItem
                label="OpenAI API Key"
                value="Configured via OPENAI_API_KEY"
                secret
              />
            </div>
          </SectionCard>

          <SectionCard title="FastAPI Interactive Docs" icon={ExternalLink}>
            <p className="text-sm text-zinc-400 mb-4">
              Explore and test all API endpoints directly in your browser using
              the built-in Swagger UI.
            </p>
            <div className="flex gap-3 flex-wrap">
              <a
                href="/api/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-md bg-zinc-800 border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
              >
                Swagger UI
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
              <a
                href="/api/redoc"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-md bg-zinc-800 border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
              >
                ReDoc
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
