"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Loader2 } from "lucide-react";

interface ReviewProgressProps {
  reviewId: number;
  initialStatus?: string;
  onComplete?: () => void;
}

interface PipelineEvent {
  event_type: string;
  message: string;
  stage?: string;
}

const STAGES = [
  { id: "distill", label: "Context Distillation" },
  { id: "reason", label: "Deep Reasoning" },
  { id: "validate", label: "Finding Validation" },
];

export function ReviewProgress({ reviewId, initialStatus, onComplete }: ReviewProgressProps) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState(initialStatus || "PENDING");
  const [activeStage, setActiveStage] = useState<string | null>(null);
  const [completedStages, setCompletedStages] = useState<string[]>([]);

  useEffect(() => {
    if (status === "COMPLETED" || status === "FAILED") return;

    const eventSource = new EventSource(`/api/v3/events/${reviewId}`);

    eventSource.onmessage = (event) => {
      try {
        const data: PipelineEvent & { stage?: string } = JSON.parse(event.data);

        if (data.event_type === "REVIEW_STARTED") {
          setStatus("RUNNING");
        } else if (data.event_type === "STAGE_STARTED") {
          setActiveStage(data.stage ?? null);
        } else if (data.event_type === "STAGE_COMPLETED") {
          setCompletedStages((prev) => {
            const stage = data.stage ?? "";
            return prev.includes(stage) ? prev : [...prev, stage];
          });
          setActiveStage(null);
        } else if (data.event_type === "REVIEW_COMPLETED") {
          setStatus("COMPLETED");
          setCompletedStages(["distill", "reason", "validate"]);
          setActiveStage(null);
          onComplete?.();
          eventSource.close();
        } else if (data.event_type === "REVIEW_FAILED") {
          setStatus("FAILED");
          setActiveStage(null);
          eventSource.close();
        }

        setEvents((prev) => [...prev, data].slice(-6));
      } catch (err) {
        console.error("Failed to parse SSE event", err);
      }
    };

    eventSource.onerror = () => {
      console.error("SSE connection error");
    };

    return () => eventSource.close();
  }, [reviewId, status, onComplete]);

  // Hybrid auto-transition simulation when no real stage events are received
  useEffect(() => {
    if (status !== "RUNNING") return;

    // If we detect any real stage events in the log, we disable simulation
    const hasRealStageEvents = events.some(
      (e) => e.event_type === "STAGE_STARTED" || e.event_type === "STAGE_COMPLETED"
    );
    if (hasRealStageEvents) return;

    let timer: NodeJS.Timeout;

    // Start with distill stage active
    if (completedStages.length === 0 && activeStage !== "distill") {
      setActiveStage("distill");
    }

    // After 3.5 seconds, complete distill and move to reasoning
    if (activeStage === "distill") {
      timer = setTimeout(() => {
        setCompletedStages(["distill"]);
        setActiveStage("reason");
      }, 3500);
    }

    // After another 8 seconds, complete reasoning and move to validation
    if (activeStage === "reason") {
      timer = setTimeout(() => {
        setCompletedStages(["distill", "reason"]);
        setActiveStage("validate");
      }, 8000);
    }

    return () => clearTimeout(timer);
  }, [status, activeStage, completedStages, events]);

  const progress = completedStages.length / STAGES.length;

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-[15px] font-bold text-white">Pipeline Progress</h3>
        <span
          className={`text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border ${
            status === "RUNNING"
              ? "bg-violet-500/10 border-violet-500/20 text-violet-400"
              : status === "COMPLETED"
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              : status === "FAILED"
              ? "bg-rose-500/10 border-rose-500/20 text-rose-400"
              : "bg-white/5 border-white/10 text-white/40"
          }`}
        >
          {status}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-white/[0.06] mb-8 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 transition-all duration-700"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Stages */}
      <div className="flex items-start justify-between relative">
        {/* Connector line */}
        <div className="absolute top-5 left-0 right-0 h-px bg-white/[0.06] -z-10" />

        {STAGES.map((stage) => {
          const isCompleted = completedStages.includes(stage.id);
          const isActive = activeStage === stage.id;

          return (
            <div key={stage.id} className="flex flex-col items-center gap-3 bg-[#0d0d14] px-3">
              <div
                className={`h-10 w-10 rounded-full flex items-center justify-center border-2 transition-all duration-500 ${
                  isCompleted
                    ? "border-emerald-500 bg-emerald-500/10 shadow-[0_0_12px_-2px_rgba(16,185,129,0.3)]"
                    : isActive
                    ? "border-violet-500 bg-violet-500/10 shadow-[0_0_12px_-2px_rgba(139,92,246,0.4)]"
                    : "border-white/10 bg-white/[0.03]"
                }`}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                ) : isActive ? (
                  <Loader2 className="h-5 w-5 text-violet-400 animate-spin" />
                ) : (
                  <CircleDashed className="h-5 w-5 text-white/20" />
                )}
              </div>
              <span
                className={`text-[11px] font-semibold text-center ${
                  isActive
                    ? "text-violet-400"
                    : isCompleted
                    ? "text-emerald-400"
                    : "text-white/25"
                }`}
              >
                {stage.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Live log */}
      <div className="mt-6 rounded-xl bg-black/30 border border-white/[0.05] p-4 font-mono text-[11px] h-24 overflow-y-auto">
        {events.map((ev, i) => (
          <div key={i} className="mb-1 flex gap-2">
            <span className="text-white/20 shrink-0">[{new Date().toLocaleTimeString()}]</span>
            <span
              className={
                ev.event_type.includes("ERROR") || ev.event_type.includes("FAILED")
                  ? "text-rose-400 shrink-0"
                  : "text-emerald-400 shrink-0"
              }
            >
              {ev.event_type}:
            </span>
            <span className="text-white/50">{ev.message}</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-white/20 animate-pulse">Waiting for pipeline events...</div>
        )}
      </div>
    </div>
  );
}
