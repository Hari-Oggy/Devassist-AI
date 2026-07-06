import { useState } from "react";
import { Bold, Italic, Code, Link, List } from "lucide-react";

export function CommentComposer({ onSubmit, onCancel }: { onSubmit: (val: string) => void, onCancel?: () => void }) {
  const [val, setVal] = useState("");
  return (
    <div className="border border-white/20 rounded-lg overflow-hidden bg-[#0d1117] text-white">
      <div className="flex items-center gap-1 border-b border-white/10 p-1 bg-white/5">
        <button aria-label="Bold" title="Bold" className="p-1.5 hover:bg-white/10 rounded text-white/60">
          <Bold className="w-4 h-4" />
        </button>
        <button aria-label="Italic" title="Italic" className="p-1.5 hover:bg-white/10 rounded text-white/60">
          <Italic className="w-4 h-4" />
        </button>
        <button aria-label="Code" title="Code" className="p-1.5 hover:bg-white/10 rounded text-white/60">
          <Code className="w-4 h-4" />
        </button>
        <button aria-label="Link" title="Link" className="p-1.5 hover:bg-white/10 rounded text-white/60">
          <Link className="w-4 h-4" />
        </button>
        <button aria-label="List" title="List" className="p-1.5 hover:bg-white/10 rounded text-white/60">
          <List className="w-4 h-4" />
        </button>
      </div>
      <textarea
        className="w-full bg-transparent p-3 text-sm focus:outline-none min-h-[100px] resize-y"
        placeholder="Write a comment..."
        value={val}
        onChange={(e) => setVal(e.target.value)}
      />
      <div className="flex justify-end gap-2 p-2 bg-white/5 border-t border-white/10">
        {onCancel && <button onClick={onCancel} className="px-3 py-1 text-xs font-semibold text-white/70 hover:text-white">Cancel</button>}
        <button onClick={() => onSubmit(val)} className="px-3 py-1 text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white rounded">Comment</button>
      </div>
    </div>
  );
}
