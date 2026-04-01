import { useEffect, useMemo, useState } from "react";
import {
  Timer,
  Search,
  Plus,
  Trash2,
  PauseCircle,
  PlayCircle,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type {
  Automation,
  AutomationListResult,
  AutomationToggleResult,
  AutomationCreateResult,
  AutomationDeleteResult,
  AutomationPauseResult,
} from "@/types/rpc";

const TRIGGER_LABELS: Record<string, string> = {
  schedule: "Schedule",
  file_event: "File Event",
  startup: "On Startup",
  pattern: "Pattern",
};

export default function AutomationManager() {
  const automations = useNeoStore((s) => s.automations);
  const setAutomations = useNeoStore((s) => s.setAutomations);
  const paused = useNeoStore((s) => s.automationsPaused);
  const setPaused = useNeoStore((s) => s.setAutomationsPaused);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    rpc<AutomationListResult>("neo.automation.list")
      .then((res) => setAutomations(res.automations))
      .catch(console.error);
  }, [setAutomations]);

  const handleToggle = async (auto: Automation) => {
    const newEnabled = auto.is_enabled === 0;
    const prev = [...automations];

    setAutomations(
      automations.map((a) =>
        a.id === auto.id ? { ...a, is_enabled: newEnabled ? 1 : 0 } : a,
      ),
    );

    try {
      await rpc<AutomationToggleResult>("neo.automation.toggle", {
        id: auto.id,
        enabled: newEnabled,
      });
    } catch (err) {
      setAutomations(prev);
      console.error("Failed to toggle automation:", err);
    }
  };

  const handleDelete = async (auto: Automation) => {
    const prev = [...automations];
    setAutomations(automations.filter((a) => a.id !== auto.id));

    try {
      await rpc<AutomationDeleteResult>("neo.automation.delete", {
        id: auto.id,
      });
    } catch (err) {
      setAutomations(prev);
      console.error("Failed to delete automation:", err);
    }
  };

  const handlePauseAll = async () => {
    const method = paused
      ? "neo.automation.resume_all"
      : "neo.automation.pause_all";
    try {
      const res = await rpc<AutomationPauseResult>(method);
      setPaused(res.paused);
    } catch (err) {
      console.error("Failed to toggle pause:", err);
    }
  };

  const searchLower = search.toLowerCase();
  const filtered = useMemo(
    () =>
      automations.filter(
        (a) =>
          a.name.toLowerCase().includes(searchLower) ||
          a.command.toLowerCase().includes(searchLower),
      ),
    [automations, searchLower],
  );

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Timer className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Automations</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePauseAll}
              className={cn(
                "flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs transition-colors",
                paused
                  ? "bg-destructive/10 text-destructive"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/80",
              )}
            >
              {paused ? (
                <>
                  <PlayCircle className="w-3.5 h-3.5" /> Resume All
                </>
              ) : (
                <>
                  <PauseCircle className="w-3.5 h-3.5" /> Pause All
                </>
              )}
            </button>
            <span className="text-xs text-muted-foreground">
              {automations.filter((a) => a.is_enabled).length}/
              {automations.length} active
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search automations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:border-primary/50 transition-colors placeholder:text-muted-foreground"
            />
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1 bg-primary/10 text-primary rounded-lg px-3 py-2 text-sm hover:bg-primary/20 transition-colors"
          >
            {showForm ? (
              <X className="w-4 h-4" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            {showForm ? "Cancel" : "Create"}
          </button>
        </div>
      </div>

      {showForm && (
        <CreateForm
          onCreated={(auto) => {
            setAutomations([...automations, auto]);
            setShowForm(false);
          }}
        />
      )}

      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {filtered.map((auto) => (
          <AutomationCard
            key={auto.id}
            automation={auto}
            onToggle={handleToggle}
            onDelete={handleDelete}
          />
        ))}
        {filtered.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-8">
            No automations found.
          </p>
        )}
      </div>
    </div>
  );
}

function AutomationCard({
  automation,
  onToggle,
  onDelete,
}: {
  automation: Automation;
  onToggle: (a: Automation) => void;
  onDelete: (a: Automation) => void;
}) {
  let triggerConfig: Record<string, unknown> = {};
  try {
    triggerConfig = JSON.parse(automation.trigger_config);
  } catch {
    /* ignore */
  }

  const triggerDetail =
    automation.trigger_type === "schedule"
      ? (triggerConfig.cron as string) || ""
      : automation.trigger_type === "file_event"
        ? (triggerConfig.path as string) || ""
        : "";

  return (
    <div className="flex items-start gap-4 bg-card border border-border rounded-xl p-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm">{automation.name}</span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full",
              automation.trigger_type === "schedule"
                ? "bg-primary/10 text-primary"
                : "bg-emerald-500/10 text-emerald-400",
            )}
          >
            {TRIGGER_LABELS[automation.trigger_type] || automation.trigger_type}
          </span>
          {automation.last_status && (
            <span
              className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full",
                automation.last_status === "success"
                  ? "bg-emerald-500/10 text-emerald-400"
                  : automation.last_status === "error"
                    ? "bg-destructive/10 text-destructive"
                    : "bg-secondary text-muted-foreground",
              )}
            >
              {automation.last_status}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-1">
          {automation.command}
        </p>
        {triggerDetail && (
          <span className="text-[10px] bg-secondary px-1.5 py-0.5 rounded text-muted-foreground">
            {triggerDetail}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onDelete(automation)}
          className="p-1 text-muted-foreground hover:text-destructive transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
        <button
          onClick={() => onToggle(automation)}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors",
            automation.is_enabled ? "bg-primary" : "bg-secondary",
          )}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5",
              automation.is_enabled
                ? "translate-x-4 ml-0.5"
                : "translate-x-0.5",
            )}
          />
        </button>
      </div>
    </div>
  );
}

function CreateForm({
  onCreated,
}: {
  onCreated: (auto: Automation) => void;
}) {
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<string>("schedule");
  const [schedule, setSchedule] = useState("");
  const [path, setPath] = useState("");
  const [command, setCommand] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !command) return;

    setSubmitting(true);
    try {
      const triggerConfig: Record<string, unknown> = {};
      if (triggerType === "schedule") {
        triggerConfig.cron = schedule;
      } else if (triggerType === "file_event") {
        triggerConfig.path = path;
        triggerConfig.pattern = "*";
        triggerConfig.event_types = ["created", "modified"];
      }

      const res = await rpc<AutomationCreateResult>("neo.automation.create", {
        name,
        trigger_type: triggerType,
        command,
        trigger_config: triggerConfig,
      });
      onCreated(res.automation);
    } catch (err) {
      console.error("Failed to create automation:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-b border-border px-6 py-4 space-y-3 bg-card/50"
    >
      <input
        type="text"
        placeholder="Automation name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-primary/50"
        required
      />

      <div className="flex gap-2">
        <select
          value={triggerType}
          onChange={(e) => setTriggerType(e.target.value)}
          className="bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none"
        >
          <option value="schedule">Schedule</option>
          <option value="file_event">File Event</option>
          <option value="startup">On Startup</option>
        </select>

        {triggerType === "schedule" && (
          <input
            type="text"
            placeholder="Cron: */30 * * * *"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
        )}

        {triggerType === "file_event" && (
          <input
            type="text"
            placeholder="Watch path: ~/Downloads"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
        )}
      </div>

      <input
        type="text"
        placeholder="Command to execute"
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-primary/50"
        required
      />

      <button
        type="submit"
        disabled={submitting || !name || !command}
        className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {submitting ? "Creating..." : "Create Automation"}
      </button>
    </form>
  );
}
