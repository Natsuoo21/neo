import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList, Search, Download, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { ActionLogEntry, ActionsRecentResult } from "@/types/rpc";

export default function ActionLog() {
  const actions = useNeoStore((s) => s.actions);
  const setActions = useNeoStore((s) => s.setActions);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    rpc<ActionsRecentResult>("neo.actions.recent", { limit: 100 })
      .then((res) => setActions(res.actions))
      .catch(console.error);
  }, [setActions]);

  const searchLower = search.toLowerCase();
  const filtered = useMemo(
    () =>
      actions.filter(
        (a) =>
          a.input_text.toLowerCase().includes(searchLower) ||
          a.tool_used.toLowerCase().includes(searchLower) ||
          a.model_used.toLowerCase().includes(searchLower),
      ),
    [actions, searchLower],
  );

  const exportCSV = useCallback(() => {
    const headers = ["Time", "Command", "Tool", "Model", "Tier", "Status", "Duration (ms)", "Tokens", "Cost (BRL)"];
    const rows = actions.map((a) => [
      a.created_at,
      `"${a.input_text.replace(/"/g, '""')}"`,
      a.tool_used,
      a.model_used,
      a.routed_tier,
      a.status,
      a.duration_ms,
      a.tokens_used,
      a.cost_brl,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    downloadFile(csv, "neo-actions.csv", "text/csv");
  }, [actions]);

  const exportJSON = useCallback(() => {
    const json = JSON.stringify(actions, null, 2);
    downloadFile(json, "neo-actions.json", "application/json");
  }, [actions]);

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Action Log</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={exportCSV}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Export as CSV"
            >
              <Download className="w-3.5 h-3.5" />
              CSV
            </button>
            <button
              onClick={exportJSON}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Export as JSON"
            >
              <Download className="w-3.5 h-3.5" />
              JSON
            </button>
            <span className="text-xs text-muted-foreground ml-2">
              {actions.length} entries
            </span>
          </div>
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
              <th className="px-2 py-2 w-6" />
              <th className="px-3 py-2 font-medium">Command</th>
              <th className="px-3 py-2 font-medium">Tool</th>
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Duration</th>
              <th className="px-6 py-2 font-medium text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((action) => (
              <ActionRow
                key={action.id}
                action={action}
                expanded={expandedId === action.id}
                onToggle={() =>
                  setExpandedId(expandedId === action.id ? null : action.id)
                }
              />
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-muted-foreground">
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

function ActionRow({
  action,
  expanded,
  onToggle,
}: {
  action: ActionLogEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="border-b border-border/50 hover:bg-card/50 transition-colors cursor-pointer"
      >
        <td className="px-2 py-2.5 text-muted-foreground">
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </td>
        <td className="px-3 py-2.5 max-w-[300px] truncate">
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
      {expanded && (
        <tr className="bg-card/30">
          <td colSpan={7} className="px-6 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <DetailField label="Tier" value={action.routed_tier || "-"} />
              <DetailField label="Skill" value={action.skill_used || "-"} />
              <DetailField label="Intent" value={action.intent || "-"} />
              <DetailField
                label="Tokens"
                value={action.tokens_used ? action.tokens_used.toLocaleString() : "-"}
              />
              <DetailField
                label="Cost"
                value={action.cost_brl ? `R$${action.cost_brl.toFixed(4)}` : "-"}
              />
              <DetailField label="ID" value={String(action.id)} />
            </div>
            {action.input_text.length > 60 && (
              <div className="mt-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Full command: </span>
                {action.input_text}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground">{label}: </span>
      <span className="text-foreground">{value}</span>
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

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
