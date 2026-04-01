import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList, Download, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import PageHeader from "./ui/PageHeader";
import SearchInput from "./ui/SearchInput";
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
      <PageHeader icon={ClipboardList} title="Action Log" subtitle={`${actions.length} entries`}>
        <button
          onClick={exportCSV}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground active:scale-95 transition-interaction"
          title="Export as CSV"
        >
          <Download className="w-3.5 h-3.5" />
          CSV
        </button>
        <button
          onClick={exportJSON}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground active:scale-95 transition-interaction"
          title="Export as JSON"
        >
          <Download className="w-3.5 h-3.5" />
          JSON
        </button>
      </PageHeader>

      <div className="px-3 md:px-6 py-3 border-b border-border/60">
        <SearchInput value={search} onChange={setSearch} placeholder="Search by command, tool, or model..." />
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-[13px]">
          <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
            <tr className="border-b border-border text-left">
              <th className="px-2 py-2 w-6" />
              <th className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Command</th>
              <th className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Tool</th>
              <th className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Model</th>
              <th className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Status</th>
              <th className="px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground text-right">Duration</th>
              <th className="px-6 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground text-right">Time</th>
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
                <td colSpan={7} className="px-6 py-8 text-center text-muted-foreground text-[13px]">
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
        className="border-b border-border/30 hover:bg-card/60 transition-interaction cursor-pointer"
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
        <td className="px-3 py-2.5 text-muted-foreground font-mono text-xs">
          {action.tool_used || "-"}
        </td>
        <td className="px-3 py-2.5 text-muted-foreground font-mono text-xs">
          {action.model_used || "-"}
        </td>
        <td className="px-3 py-2.5">
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
              action.status === "success"
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-destructive/10 text-destructive",
            )}
          >
            {action.status}
          </span>
        </td>
        <td className="px-3 py-2.5 text-right text-muted-foreground font-mono text-xs tabular-nums">
          {action.duration_ms}ms
        </td>
        <td className="px-6 py-2.5 text-right text-muted-foreground text-xs">
          {formatTime(action.created_at)}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-card/40 border-b border-border/30">
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
      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{label}: </span>
      <span className="text-foreground font-mono">{value}</span>
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
