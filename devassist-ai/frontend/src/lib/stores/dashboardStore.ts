import { create } from "zustand";
import { apiFetch } from "@/lib/api";

export interface StatusData {
  status: string;
  database: boolean;
  llm_provider: string;
  llm_model: string;
  version: string;
}

export interface ReviewStats {
  total: number;
  completed: number;
  failed: number;
  running: number;
}

export interface FindingSeverity {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface FindingCategory {
  name: string;
  count: number;
}

export interface AnalyticsData {
  reviews: ReviewStats;
  findings_by_severity: FindingSeverity;
  findings_by_category: FindingCategory[];
  total_findings: number;
  total_repositories: number;
  avg_findings_per_review: number;
  avg_resolution_time?: number;
}

export interface ReviewItem {
  id: number;
  status: string;
  summary: string | null;
  commit_sha: string | null;
  created_at: string;
  completed_at: string | null;
  pr_title: string | null;
  pr_number: number | null;
  repo_name: string | null;
  provider: string | null;
  total_findings: number;
}

export interface TrendItem {
  date: string;
  critical: number;
  high: number;
  other: number;
}

export interface Repository {
  id: number;
  provider: string;
  full_name: string;
  default_branch: string;
  is_active: boolean;
  created_at: string;
  reviewsCount?: number;
  openIssues?: number;
  successRate?: number;
  reviews_count?: number;
  open_issues?: number;
  success_rate?: number;
}

export interface PipelineSettings {
  review_mode: string;
  llm_model: string;
  llm_provider: string;
  rag_enabled: boolean;
}

// ── Default safe values used as fallbacks on network error ──────────────────
const DEFAULT_ANALYTICS: AnalyticsData = {
  reviews: { total: 0, completed: 0, failed: 0, running: 0 },
  findings_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
  findings_by_category: [],
  total_findings: 0,
  total_repositories: 0,
  avg_findings_per_review: 0,
  avg_resolution_time: 0,
};

interface DashboardState {
  // Data
  statusData: StatusData | null;
  analytics: AnalyticsData | null;
  reviews: ReviewItem[];
  repositories: Repository[];
  trends: TrendItem[];
  pipelineSettings: PipelineSettings | null;

  // Loading states
  loadingStatus: boolean;
  loadingAnalytics: boolean;
  loadingReviews: boolean;
  loadingRepositories: boolean;
  loadingTrends: boolean;
  loadingPipeline: boolean;

  // Global connection error flag
  connectionError: string | null;

  // Actions
  fetchStatus: () => Promise<void>;
  fetchAnalytics: () => Promise<void>;
  fetchReviews: () => Promise<void>;
  fetchRepositories: () => Promise<void>;
  fetchTrends: () => Promise<void>;
  fetchPipelineSettings: () => Promise<void>;
  fetchAll: () => Promise<void>;
  setReviewMode: (mode: string) => Promise<void>;
  addRepository: (data: { provider: string; full_name: string; default_branch: string }) => Promise<void>;
  removeRepository: (id: number) => Promise<void>;
  clearConnectionError: () => void;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  statusData: null,
  analytics: null,
  reviews: [],
  repositories: [],
  trends: [],
  pipelineSettings: null,
  loadingStatus: false,
  loadingAnalytics: false,
  loadingReviews: false,
  loadingRepositories: false,
  loadingTrends: false,
  loadingPipeline: false,
  connectionError: null,

  clearConnectionError: () => set({ connectionError: null }),

  fetchStatus: async () => {
    set({ loadingStatus: true });
    try {
      const data = await apiFetch<StatusData>("/api/v3/status");
      set({ statusData: data, connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchStatus:", msg);
      set({ connectionError: msg });
    } finally {
      set({ loadingStatus: false });
    }
  },

  fetchAnalytics: async () => {
    set({ loadingAnalytics: true });
    try {
      const data = await apiFetch<AnalyticsData>("/api/v3/analytics");
      set({ analytics: data, connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchAnalytics:", msg);
      // Use safe defaults so UI still renders
      set({ analytics: DEFAULT_ANALYTICS, connectionError: msg });
    } finally {
      set({ loadingAnalytics: false });
    }
  },

  fetchReviews: async () => {
    set({ loadingReviews: true });
    try {
      const data = await apiFetch<ReviewItem[]>("/api/v3/reviews");
      set({ reviews: Array.isArray(data) ? data : [], connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchReviews:", msg);
      set({ reviews: [], connectionError: msg });
    } finally {
      set({ loadingReviews: false });
    }
  },

  fetchRepositories: async () => {
    set({ loadingRepositories: true });
    try {
      const data = await apiFetch<Repository[]>("/api/v3/repositories");
      set({ repositories: Array.isArray(data) ? data : [], connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchRepositories:", msg);
      set({ repositories: [], connectionError: msg });
    } finally {
      set({ loadingRepositories: false });
    }
  },

  fetchTrends: async () => {
    set({ loadingTrends: true });
    try {
      const data = await apiFetch<TrendItem[]>("/api/v3/analytics/trends");
      set({ trends: Array.isArray(data) ? data : [], connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchTrends:", msg);
      set({ trends: [] });
    } finally {
      set({ loadingTrends: false });
    }
  },

  fetchPipelineSettings: async () => {
    set({ loadingPipeline: true });
    try {
      const data = await apiFetch<PipelineSettings>("/api/v3/settings");
      set({ pipelineSettings: data, connectionError: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cannot reach backend";
      console.error("[store] fetchPipelineSettings:", msg);
    } finally {
      set({ loadingPipeline: false });
    }
  },

  fetchAll: async () => {
    const { fetchStatus, fetchAnalytics, fetchReviews, fetchRepositories, fetchTrends, fetchPipelineSettings } =
      get();
    await Promise.allSettled([
      fetchStatus(),
      fetchAnalytics(),
      fetchReviews(),
      fetchRepositories(),
      fetchTrends(),
      fetchPipelineSettings(),
    ]);
  },

  setReviewMode: async (mode: string) => {
    const data = await apiFetch<PipelineSettings>("/api/v3/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_mode: mode }),
    });
    set({ pipelineSettings: data });
  },

  addRepository: async (repoData) => {
    await apiFetch<unknown>("/api/v3/repositories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(repoData),
    });
    await get().fetchRepositories();
  },

  removeRepository: async (id: number) => {
    await apiFetch<unknown>(`/api/v3/repositories/${id}`, { method: "DELETE" });
    await get().fetchRepositories();
  },
}));
