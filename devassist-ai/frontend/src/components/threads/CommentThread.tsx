"use client";

import { CommentThreadOut } from "@/lib/api/threads";
import { ThreadBadge } from "./ThreadBadge";
import { CommentComposer } from "./CommentComposer";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function CommentThread({ thread, reviewId }: { thread: CommentThreadOut, reviewId: number }) {
  const [replying, setReplying] = useState(false);
  const queryClient = useQueryClient();

  const addCommentMutation = useMutation({
    mutationFn: async (body: string) => {
      const res = await fetch(`/api/v3/reviews/${reviewId}/threads/${thread.id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body })
      });
      if (!res.ok) throw new Error("Failed to add comment");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads", reviewId] });
      setReplying(false);
    }
  });

  return (
    <div className="border border-white/10 rounded-lg bg-black/40 overflow-hidden my-2">
      <div className="flex items-center justify-between p-3 border-b border-white/5 bg-white/5">
        <ThreadBadge status={thread.status} />
        {thread.resolved && <span className="text-xs text-emerald-500 font-semibold">Resolved</span>}
      </div>
      <div className="p-0">
        {thread.comments?.map(c => (
          <div key={c.id} className="p-3 border-b border-white/5">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-sm text-white/90">{c.author}</span>
              {c.is_bot && <span className="bg-violet-500/20 text-violet-400 px-1.5 py-0.5 rounded text-[10px]">BOT</span>}
            </div>
            <div className="text-sm text-white/80 whitespace-pre-wrap">{c.body}</div>
          </div>
        ))}
      </div>
      <div className="p-3 bg-white/[0.02]">
        {replying ? (
          <CommentComposer onSubmit={(val) => addCommentMutation.mutate(val)} onCancel={() => setReplying(false)} />
        ) : (
          <button onClick={() => setReplying(true)} className="text-xs text-white/50 hover:text-white">
            Reply to thread...
          </button>
        )}
      </div>
    </div>
  );
}
