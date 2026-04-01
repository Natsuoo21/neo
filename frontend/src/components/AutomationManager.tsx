import { useEffect, useMemo, useState } from "react";
import {
  Timer,
  Plus,
  Trash2,
  PauseCircle,
  PlayCircle,
  Pencil,
  Play,
  X,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import PageHeader from "./ui/PageHeader";
import SearchInput from "./ui/SearchInput";
import Toggle from "./ui/Toggle";
import EmptyState from "./ui/EmptyState";
import type {
  Automation,
  AutomationListResult,
  AutomationToggleResult,
  AutomationCreateResult,
  AutomationDeleteResult,
  AutomationPauseResult,
  AutomationRunResult,
} from "@/types/rpc";

const TRIGGER_LABELS: Record<string, string> = {
  schedule: "Schedule",
  file_event: "File Event",
  startup: "On Startup",
  pattern: "Pattern",
};

const INPUT_CLASS =
  "w-full bg-card border border-border rounded-md px-3 py-2 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground";

export default function AutomationManager() {
  const automations = useNeoStore((s) => s.automations);
  const setAutomations = useNeoStore((s) => s.setAutomations);
  const paused = useNeoStore((s) => s.automationsPaused);
  const setPaused = useNeoStore((s) => s.setAutomationsPaused);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

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

  const handleRun = async (auto: Automation) => {
    try {
      await rpc<AutomationRunResult>("neo.automation.run", { id: auto.id });
    } catch (err) {
      console.error("Failed to run automation:", err);
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
      <PageHeader icon={Timer} title="Automations" subtitle={`${automations.filter((a) => a.is_enabled).length}/${automations.length} active`}>
        <button
          onClick={handlePauseAll}
          className={cn(
            "flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium active:scale-95 transition-interaction",
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
      </PageHeader>

      <div className="px-6 py-3 border-b border-border/60 flex gap-2">
        <div className="flex-1">
          <SearchInput value={search} onChange={setSearch} placeholder="Search automations..." />
        </div>
        <button
          onClick={() => {
            setShowForm(!showForm);
            setEditingId(null);
          }}
          className="flex items-center gap-1 bg-primary/10 text-primary rounded-md px-3 py-2 text-[13px] font-medium hover:bg-primary/20 active:scale-[0.98] transition-interaction"
        >
          {showForm ? (
            <X className="w-4 h-4" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          {showForm ? "Cancel" : "Create"}
        </button>
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
        {filtered.map((auto, i) =>
          editingId === auto.id ? (
            <EditForm
              key={auto.id}
              automation={auto}
              onSaved={(updated) => {
                setAutomations(
                  automations.map((a) => (a.id === updated.id ? updated : a)),
                );
                setEditingId(null);
              }}
              onCancel={() => setEditingId(null)}
            />
          ) : (
            <AutomationCard
              key={auto.id}
              automation={auto}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onEdit={() => setEditingId(auto.id)}
              onRun={handleRun}
              index={i}
            />
          ),
        )}
        {filtered.length === 0 && (
          <EmptyState icon={Timer} title="No automations found" description="Create one to get started." />
        )}
      </div>
    </div>
  );
}

function AutomationCard({
  automation,
  onToggle,
  onDelete,
  onEdit,
  onRun,
  index,
}: {
  automation: Automation;
  onToggle: (a: Automation) => void;
  onDelete: (a: Automation) => void;
  onEdit: () => void;
  onRun: (a: Automation) => void;
  index: number;
}) {
  const [running, setRunning] = useState(false);

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

  const handleRun = async () => {
    setRunning(true);
    try {
      await onRun(automation);
    } finally {
      setTimeout(() => setRunning(false), 2000);
    }
  };

  return (
    <div
      className="flex items-start gap-4 bg-card border border-border/60 rounded-[10px] p-4 shadow-card animate-fade-in-up"
      style={{ animationDelay: `${index * 30}ms` }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-[13px]">{automation.name}</span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
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
                "text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
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
        <p className="text-xs text-muted-foreground mb-1 font-mono">
          {automation.command}
        </p>
        <div className="flex items-center gap-2">
          {triggerDetail && (
            <span className="text-[10px] bg-secondary px-1.5 py-0.5 rounded-[var(--radius-sm)] text-muted-foreground font-mono">
              {triggerDetail}
            </span>
          )}
          {automation.last_run_at && (
            <span className="text-[10px] text-muted-foreground">
              Last run: {formatTime(automation.last_run_at)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <button
          onClick={handleRun}
          disabled={running}
          className="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-accent/50 active:scale-90 transition-interaction disabled:opacity-40"
          title="Run now"
        >
          {running ? (
            <Check className="w-4 h-4 text-emerald-400" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </button>
        <button
          onClick={onEdit}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50 active:scale-90 transition-interaction"
          title="Edit"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          onClick={() => onDelete(automation)}
          className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 active:scale-90 transition-interaction"
          title="Delete"
        >
          <Trash2 className="w-4 h-4" />
        </button>
        <Toggle enabled={!!automation.is_enabled} onToggle={() => onToggle(automation)} />
      </div>
    </div>
  );
}

function EditForm({
  automation,
  onSaved,
  onCancel,
}: {
  automation: Automation;
  onSaved: (a: Automation) => void;
  onCancel: () => void;
}) {
  let initialConfig: Record<string, unknown> = {};
  try {
    initialConfig = JSON.parse(automation.trigger_config);
  } catch {
    /* ignore */
  }

  const [name, setName] = useState(automation.name);
  const [command, setCommand] = useState(automation.command);
  const [schedule, setSchedule] = useState(
    (initialConfig.cron as string) || "",
  );
  const [path, setPath] = useState((initialConfig.path as string) || "");
  const [submitting, setSubmitting] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !command) return;

    setSubmitting(true);
    try {
      // Delete old and recreate (backend doesn't have update endpoint)
      await rpc<AutomationDeleteResult>("neo.automation.delete", {
        id: automation.id,
      });

      const triggerConfig: Record<string, unknown> = {};
      if (automation.trigger_type === "schedule") {
        triggerConfig.cron = schedule;
      } else if (automation.trigger_type === "file_event") {
        triggerConfig.path = path;
        triggerConfig.pattern = initialConfig.pattern || "*";
        triggerConfig.event_types = initialConfig.event_types || [
          "created",
          "modified",
        ];
      }

      const res = await rpc<AutomationCreateResult>(
        "neo.automation.create",
        {
          name,
          trigger_type: automation.trigger_type,
          command,
          trigger_config: triggerConfig,
        },
      );
      onSaved(res.automation);
    } catch (err) {
      console.error("Failed to update automation:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSave}
      className="bg-card border border-primary/30 rounded-[10px] p-4 space-y-3 shadow-card"
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-primary uppercase tracking-wider">Editing</span>
        <button
          type="button"
          onClick={onCancel}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 active:scale-95 transition-interaction"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Automation name"
        className={INPUT_CLASS}
        required
      />
      <div className="flex gap-2">
        <div className="bg-secondary rounded-md px-3 py-2 text-[13px] text-muted-foreground">
          {TRIGGER_LABELS[automation.trigger_type] || automation.trigger_type}
        </div>
        {automation.trigger_type === "schedule" && (
          <input
            type="text"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            placeholder="Cron: */30 * * * *"
            className={cn(INPUT_CLASS, "flex-1")}
          />
        )}
        {automation.trigger_type === "file_event" && (
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Watch path"
            className={cn(INPUT_CLASS, "flex-1")}
          />
        )}
      </div>
      <input
        type="text"
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        placeholder="Command to execute"
        className={INPUT_CLASS}
        required
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting || !name || !command}
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-[13px] font-medium hover:brightness-110 active:scale-[0.98] transition-interaction disabled:opacity-40"
        >
          {submitting ? "Saving..." : "Save Changes"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="bg-secondary text-muted-foreground rounded-md px-4 py-2 text-[13px] hover:bg-secondary/80 active:scale-[0.98] transition-interaction"
        >
          Cancel
        </button>
      </div>
    </form>
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
      className="border-b border-border/60 px-6 py-4 space-y-3 bg-card/50"
    >
      <input
        type="text"
        placeholder="Automation name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className={INPUT_CLASS}
        required
      />

      <div className="flex gap-2">
        <select
          value={triggerType}
          onChange={(e) => setTriggerType(e.target.value)}
          className="bg-card border border-border rounded-md px-3 py-2 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all"
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
            className={cn(INPUT_CLASS, "flex-1")}
          />
        )}

        {triggerType === "file_event" && (
          <input
            type="text"
            placeholder="Watch path: ~/Downloads"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className={cn(INPUT_CLASS, "flex-1")}
          />
        )}
      </div>

      <input
        type="text"
        placeholder="Command to execute"
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        className={INPUT_CLASS}
        required
      />

      <button
        type="submit"
        disabled={submitting || !name || !command}
        className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-[13px] font-medium hover:brightness-110 active:scale-[0.98] transition-interaction disabled:opacity-40"
      >
        {submitting ? "Creating..." : "Create Automation"}
      </button>
    </form>
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
