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
}

export function ReviewProgress({ reviewId, initialStatus, onComplete }: ReviewProgressProps) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [status, setStatus] = useState(initialStatus || "PENDING");
  
  // Pipeline Stages
  const stages = [
    { id: "distill", label: "Context Distillation" },
    { id: "reason", label: "Deep Reasoning" },
    { id: "validate", label: "Finding Validation" },
  ];

  const [activeStage, setActiveStage] = useState<string | null>(null);
  const [completedStages, setCompletedStages] = useState<string[]>([]);

  useEffect(() => {
    if (status === "COMPLETED" || status === "FAILED") return;

    const eventSource = new EventSource(`/api/v3/events/${reviewId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Handle specific event types
        if (data.event_type === "REVIEW_STARTED") {
          setStatus("RUNNING");
        } else if (data.event_type === "STAGE_STARTED") {
          setActiveStage(data.stage);
        } else if (data.event_type === "STAGE_COMPLETED") {
          setCompletedStages(prev => [...prev, data.stage]);
          setActiveStage(null);
        } else if (data.event_type === "REVIEW_COMPLETED") {
          setStatus("COMPLETED");
          if (onComplete) onComplete();
          eventSource.close();
        } else if (data.event_type === "REVIEW_FAILED") {
          setStatus("FAILED");
          eventSource.close();
        }

        setEvents(prev => [...prev, data].slice(-5)); // Keep last 5 events
      } catch (err) {
        console.error("Failed to parse SSE event", err);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE connection error", error);
      // Optional: Handle reconnection logic or assume complete
    };

    return () => {
      eventSource.close();
    };
  }, [reviewId, status, onComplete]);

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-6 mb-8">
      <h3 className="text-lg font-semibold text-white mb-4">Pipeline Progress</h3>
      
      <div className="flex items-center justify-between mb-8 relative">
        {/* Progress Line */}
        <div className="absolute top-1/2 left-0 w-full h-0.5 bg-zinc-800 -z-10 -translate-y-1/2"></div>
        
        {stages.map((stage) => {
          const isCompleted = completedStages.includes(stage.id);
          const isActive = activeStage === stage.id;
          
          return (
            <div key={stage.id} className="flex flex-col items-center relative bg-zinc-900/50 px-2">
              <div className={`h-10 w-10 rounded-full flex items-center justify-center border-2 mb-2 bg-zinc-900
                ${isCompleted ? 'border-emerald-500 text-emerald-500' : 
                  isActive ? 'border-orange-500 text-orange-500 shadow-[0_0_15px_rgba(249,115,22,0.3)]' : 
                  'border-zinc-700 text-zinc-600'}`}
              >
                {isCompleted ? <CheckCircle2 className="h-5 w-5" /> :
                 isActive ? <Loader2 className="h-5 w-5 animate-spin" /> :
                 <CircleDashed className="h-5 w-5" />}
              </div>
              <span className={`text-xs font-medium ${isActive ? 'text-orange-400' : isCompleted ? 'text-emerald-400' : 'text-zinc-500'}`}>
                {stage.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Live Log */}
      <div className="bg-[#0a0a0a] rounded border border-zinc-800 p-3 font-mono text-xs text-zinc-400 h-24 overflow-y-auto">
        {events.map((ev, i) => (
          <div key={i} className="mb-1 flex gap-2">
            <span className="text-zinc-600">[{new Date().toLocaleTimeString()}]</span>
            <span className={ev.event_type.includes('ERROR') || ev.event_type.includes('FAILED') ? 'text-red-400' : 'text-emerald-400'}>
              {ev.event_type}:
            </span>
            <span className="text-zinc-300">{ev.message}</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-zinc-600 animate-pulse">Waiting for pipeline events...</div>
        )}
      </div>
    </div>
  );
}
