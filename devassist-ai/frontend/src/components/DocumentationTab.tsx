"use client";

import { useEffect, useState } from "react";
import { FileCode2, CheckCircle2, XCircle, FileText, ChevronRight } from "lucide-react";

interface DocItem {
  file: string;
  updated_code: string;
  markdown: string;
  changes_made: number;
  items_documented: string[];
}

function GlassCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-white/[0.07] bg-white/[0.03] backdrop-blur-sm p-6 ${className}`}
    >
      {children}
    </div>
  );
}

export function DocumentationTab({
  reviewId,
  isCompleted,
}: {
  reviewId: number;
  isCompleted: boolean;
}) {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<DocItem | null>(null);

  useEffect(() => {
    if (!isCompleted) {
      setLoading(false);
      return;
    }
    // Simulate fetching documentation from backend. 
    // In reality, you'd fetch from `/api/v3/reviews/${reviewId}/documentation`
    // For now, we mock it to demonstrate the UI.
    setTimeout(() => {
      setDocs([
        {
          file: "src/api/auth.py",
          updated_code: `def login(user_id: int):\n    """Authenticates the user by ID and returns a session token."""\n    pass`,
          markdown: `# auth.py\n\nHandles user authentication.\n\n## login(user_id)\nAuthenticates the user.`,
          changes_made: 1,
          items_documented: ["login"],
        },
      ]);
      setLoading(false);
    }, 1000);
  }, [reviewId, isCompleted]);

  if (!isCompleted) return null;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500/20 border-t-emerald-500" />
      </div>
    );
  }

  if (error || docs.length === 0) {
    return (
      <GlassCard className="text-center py-12">
        <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-emerald-500/50" />
        <p className="font-bold text-white text-[16px]">No Documentation Updates</p>
        <p className="text-[13px] text-white/40 mt-1">
          All files in this review are fully documented.
        </p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-6">
        {/* Left Sidebar: File List */}
        <div className="col-span-1 space-y-3">
          <h3 className="text-[13px] font-bold text-white/50 uppercase tracking-wider mb-2">
            Generated Docs
          </h3>
          {docs.map((doc, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedDoc(doc)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all duration-150 ${
                selectedDoc?.file === doc.file
                  ? "bg-emerald-500/10 border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.05)]"
                  : "bg-white/[0.02] border-white/[0.05] hover:border-white/[0.1] hover:bg-white/[0.04]"
              }`}
            >
              <FileText
                className={`h-4 w-4 shrink-0 ${
                  selectedDoc?.file === doc.file ? "text-emerald-400" : "text-white/40"
                }`}
              />
              <div className="overflow-hidden">
                <p className="text-[13px] font-mono text-white/80 truncate">
                  {doc.file}
                </p>
                <p className="text-[11px] text-white/40 mt-0.5">
                  {doc.changes_made} item(s) documented
                </p>
              </div>
            </button>
          ))}
        </div>

        {/* Right Content Area: Code Viewer */}
        <div className="col-span-2">
          {selectedDoc ? (
            <GlassCard className="h-full !p-0 overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-white/[0.05] bg-white/[0.02] flex items-center justify-between">
                <div className="flex items-center gap-2 text-[13px] font-mono font-bold text-emerald-400">
                  <FileCode2 className="h-4 w-4" />
                  {selectedDoc.file}
                </div>
                <button className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-black bg-emerald-400 rounded-lg hover:bg-emerald-300 transition-colors">
                  Approve & Merge
                </button>
              </div>
              <div className="p-5 overflow-auto bg-black/20 flex-1">
                <pre className="text-[12px] font-mono text-white/70 leading-relaxed whitespace-pre-wrap">
                  {selectedDoc.updated_code}
                </pre>
              </div>
            </GlassCard>
          ) : (
            <div className="h-full flex items-center justify-center border border-white/[0.05] border-dashed rounded-2xl bg-white/[0.01]">
              <p className="text-[13px] text-white/30 font-medium">
                Select a file to view generated documentation.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
