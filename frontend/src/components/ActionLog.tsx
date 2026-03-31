import { useEffect, useState } from "react";
import { ClipboardList, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { ActionsRecentResult } from "@/types/rpc";

export default function ActionLog() {
  const actions = useNeoStore((s) => s.actions);
  const setActions = useNeoStore((s) => s.setActions);
  const [search, setSearch] = useState("");

  useEffect(() => {
    rpc<ActionsRecentResult>("neo.actions.recent", { limit: 100 })
      .then((res) => setActions(res.actions))
      .catch(console.error);
  }, [setActions]);

  const filtered = actions.filter(
    (a) =>
      a.input_text.toLowerCase().includes(search.toLowerCase()) ||
      a.tool_used.toLowerCase().includes(search.toLowerCase()) ||
      a.model_used.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Action Log</h2>
          </div>
          <span className="text-xs text-muted-foreground">
            {actions.length} entries
          </span>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by command, tool, or model..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:border-primary/50 transition-colors placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-background">
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="px-6 py-2 font-medium">Command</th>
              <th className="px-3 py-2 font-medium">Tool</th>
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Duration</th>
              <th className="px-6 py-2 font-medium text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((action) => (
              <tr
                key={action.id}
                className="border-b border-border/50 hover:bg-card/50 transition-colors"
              >
                <td className="px-6 py-2.5 max-w-[300px] truncate">
                  {action.input_text}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">
                  {action.tool_used || "-"}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">
                  {action.model_used || "-"}
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded-full",
                      action.status === "success"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-destructive/10 text-destructive",
                    )}
                  >
                    {action.status}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right text-muted-foreground tabular-nums">
                  {action.duration_ms}ms
                </td>
                <td className="px-6 py-2.5 text-right text-muted-foreground text-xs">
                  {formatTime(action.created_at)}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No actions found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
