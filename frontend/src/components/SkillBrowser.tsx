import { useEffect, useMemo, useState } from "react";
import { Zap, Plus, X, Trash2, Download, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import PageHeader from "./ui/PageHeader";
import SearchInput from "./ui/SearchInput";
import Toggle from "./ui/Toggle";
import EmptyState from "./ui/EmptyState";
import type {
  Skill,
  SkillsListResult,
  SkillsToggleResult,
  SkillsCreateResult,
  SkillsImportResult,
  SkillsDeleteResult,
} from "@/types/rpc";

const INPUT_CLASS =
  "w-full bg-card border border-border rounded-md px-3 py-2 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground";

const TEXTAREA_CLASS =
  "w-full bg-card border border-border rounded-md px-3 py-2 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground font-mono resize-y";

type FormTab = "create" | "import";

export default function SkillBrowser() {
  const skills = useNeoStore((s) => s.skills);
  const setSkills = useNeoStore((s) => s.setSkills);
  const [search, setSearch] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formTab, setFormTab] = useState<FormTab>("create");

  const reload = () => {
    rpc<SkillsListResult>("neo.skills.list")
      .then((res) => setSkills(res.skills))
      .catch(console.error);
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setSkills]);

  const handleToggle = async (skill: Skill) => {
    const newEnabled = skill.is_enabled === 0;
    const previousSkills = [...skills];

    setSkills(
      skills.map((s) =>
        s.name === skill.name ? { ...s, is_enabled: newEnabled ? 1 : 0 } : s,
      ),
    );

    if (selectedSkill?.name === skill.name) {
      setSelectedSkill({ ...skill, is_enabled: newEnabled ? 1 : 0 });
    }

    try {
      await rpc<SkillsToggleResult>("neo.skills.toggle", {
        name: skill.name,
        enabled: newEnabled,
      });
    } catch (err) {
      setSkills(previousSkills);
      if (selectedSkill?.name === skill.name) {
        setSelectedSkill(skill);
      }
      console.error("Failed to toggle skill:", err);
    }
  };

  const handleDelete = async (skill: Skill) => {
    const prev = [...skills];
    setSkills(skills.filter((s) => s.name !== skill.name));
    if (selectedSkill?.name === skill.name) setSelectedSkill(null);

    try {
      await rpc<SkillsDeleteResult>("neo.skills.delete", { name: skill.name });
    } catch (err) {
      setSkills(prev);
      console.error("Failed to delete skill:", err);
    }
  };

  const searchLower = search.toLowerCase();
  const filtered = useMemo(
    () =>
      skills.filter(
        (s) =>
          s.name.toLowerCase().includes(searchLower) ||
          s.description.toLowerCase().includes(searchLower),
      ),
    [skills, searchLower],
  );

  return (
    <div className="flex h-full">
      {/* Skill list */}
      <div className={cn("flex flex-col", selectedSkill ? "w-1/2 border-r border-border/60" : "w-full")}>
        <PageHeader icon={Zap} title="Skills" subtitle={`${skills.filter((s) => s.is_enabled).length}/${skills.length} enabled`}>
          <div className="w-56">
            <SearchInput value={search} onChange={setSearch} placeholder="Search skills..." />
          </div>
        </PageHeader>

        <div className="px-6 py-3 border-b border-border/60 flex gap-2">
          <button
            onClick={() => {
              setShowForm(!showForm);
              setFormTab("create");
            }}
            className="flex items-center gap-1 bg-primary/10 text-primary rounded-md px-3 py-2 text-[13px] font-medium hover:bg-primary/20 active:scale-[0.98] transition-interaction"
          >
            {showForm && formTab === "create" ? (
              <X className="w-4 h-4" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            {showForm && formTab === "create" ? "Cancel" : "Create Skill"}
          </button>
          <button
            onClick={() => {
              if (showForm && formTab === "import") {
                setShowForm(false);
              } else {
                setShowForm(true);
                setFormTab("import");
              }
            }}
            className="flex items-center gap-1 bg-secondary text-muted-foreground rounded-md px-3 py-2 text-[13px] font-medium hover:bg-secondary/80 active:scale-[0.98] transition-interaction"
          >
            {showForm && formTab === "import" ? (
              <X className="w-4 h-4" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            {showForm && formTab === "import" ? "Cancel" : "Import from GitHub"}
          </button>
        </div>

        {showForm && formTab === "create" && (
          <CreateSkillForm
            onCreated={() => {
              setShowForm(false);
              reload();
            }}
          />
        )}

        {showForm && formTab === "import" && (
          <ImportSkillForm
            onImported={() => {
              setShowForm(false);
              reload();
            }}
          />
        )}

        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {filtered.map((skill, i) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              selected={selectedSkill?.id === skill.id}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onSelect={() =>
                setSelectedSkill(selectedSkill?.id === skill.id ? null : skill)
              }
              index={i}
            />
          ))}
          {filtered.length === 0 && (
            <EmptyState icon={Zap} title="No skills found" description="Create a skill or try a different search term." />
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedSkill && (
        <SkillDetail
          skill={selectedSkill}
          onClose={() => setSelectedSkill(null)}
          onToggle={handleToggle}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Skill Form
// ---------------------------------------------------------------------------

function CreateSkillForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [taskTypes, setTaskTypes] = useState("");
  const [instructions, setInstructions] = useState("");
  const [tools, setTools] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !instructions) return;

    setSubmitting(true);
    setError("");
    try {
      await rpc<SkillsCreateResult>("neo.skills.create", {
        name: name.trim(),
        description: description.trim(),
        content: instructions.trim(),
        task_types: taskTypes
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        tools: tools
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create skill");
      console.error("Failed to create skill:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-b border-border/60 px-6 py-4 space-y-3 bg-card/50"
    >
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Name
          </label>
          <input
            type="text"
            placeholder="e.g. meeting_agenda"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={INPUT_CLASS}
            required
          />
        </div>
        <div className="flex-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Description
          </label>
          <input
            type="text"
            placeholder="What this skill does"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={INPUT_CLASS}
          />
        </div>
      </div>

      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Task Types
            <span className="text-muted-foreground/60 ml-1 normal-case">(comma-separated)</span>
          </label>
          <input
            type="text"
            placeholder="meeting, agenda, notes"
            value={taskTypes}
            onChange={(e) => setTaskTypes(e.target.value)}
            className={INPUT_CLASS}
          />
        </div>
        <div className="flex-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Tools
            <span className="text-muted-foreground/60 ml-1 normal-case">(comma-separated)</span>
          </label>
          <input
            type="text"
            placeholder="create_document, create_excel"
            value={tools}
            onChange={(e) => setTools(e.target.value)}
            className={INPUT_CLASS}
          />
        </div>
      </div>

      <div>
        <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
          Instructions
          <span className="text-muted-foreground/60 ml-1 normal-case">(markdown — what the LLM should do)</span>
        </label>
        <textarea
          placeholder={"# Meeting Agenda Skill\n\nYou are helping the user create a structured meeting agenda.\n\n## Guidelines\n- Ask for attendees and topics\n- Format with time slots\n- Include action items section"}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          className={TEXTAREA_CLASS}
          rows={8}
          required
        />
      </div>

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}

      <button
        type="submit"
        disabled={submitting || !name || !instructions}
        className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-[13px] font-medium hover:brightness-110 active:scale-[0.98] transition-interaction disabled:opacity-40"
      >
        {submitting ? "Creating..." : "Create Skill"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Import from GitHub Form
// ---------------------------------------------------------------------------

function ImportSkillForm({ onImported }: { onImported: () => void }) {
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ imported: number; skills: { name: string; description: string }[] } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) return;

    setSubmitting(true);
    setError("");
    setResult(null);
    try {
      const res = await rpc<SkillsImportResult>("neo.skills.import", {
        url: url.trim(),
      });
      if (res.imported === 0) {
        setError("No valid skill files found at that URL. Files must have YAML frontmatter with at least a 'name' field.");
      } else {
        setResult(res);
        setTimeout(onImported, 2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to import");
      console.error("Failed to import skills:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-b border-border/60 px-6 py-4 space-y-3 bg-card/50"
    >
      <div>
        <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
          GitHub URL
        </label>
        <input
          type="url"
          placeholder="https://github.com/user/repo/blob/main/skills/writer.md"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className={INPUT_CLASS}
          required
        />
        <p className="text-[10px] text-muted-foreground mt-1">
          Paste a link to a single .md file or a directory. Supports blob, tree, and raw URLs.
        </p>
      </div>

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}

      {result && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-md px-3 py-2">
          <p className="text-xs text-emerald-400 font-medium">
            Imported {result.imported} skill{result.imported !== 1 ? "s" : ""}:
          </p>
          {result.skills.map((s) => (
            <p key={s.name} className="text-xs text-emerald-400/80 ml-2">
              /{s.name} — {s.description}
            </p>
          ))}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !url}
        className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-[13px] font-medium hover:brightness-110 active:scale-[0.98] transition-interaction disabled:opacity-40"
      >
        {submitting ? "Importing..." : "Import"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Skill Card
// ---------------------------------------------------------------------------

function SkillCard({
  skill,
  selected,
  onToggle,
  onDelete,
  onSelect,
  index,
}: {
  skill: Skill;
  selected: boolean;
  onToggle: (s: Skill) => void;
  onDelete: (s: Skill) => void;
  onSelect: () => void;
  index: number;
}) {
  const taskTypes = parseTaskTypes(skill.task_types);
  const canDelete = skill.skill_type !== "public";

  return (
    <div
      className={cn(
        "flex items-start gap-4 bg-card border rounded-[10px] p-4 shadow-card cursor-pointer transition-interaction animate-fade-in-up",
        selected
          ? "border-primary/40 ring-1 ring-primary/10"
          : "border-border/60 hover:shadow-elevated hover:border-border",
      )}
      style={{ animationDelay: `${index * 30}ms` }}
      onClick={onSelect}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-[13px]">{skill.name}</span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
              skill.skill_type === "public"
                ? "bg-primary/10 text-primary"
                : skill.skill_type === "community"
                  ? "bg-violet-500/10 text-violet-400"
                  : "bg-emerald-500/10 text-emerald-400",
            )}
          >
            {skill.skill_type}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mb-2">{skill.description}</p>
        <div className="flex flex-wrap gap-1">
          {taskTypes.slice(0, 6).map((t) => (
            <span
              key={t}
              className="text-[10px] bg-secondary px-1.5 py-0.5 rounded-[var(--radius-sm)] text-muted-foreground"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        {canDelete && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(skill);
            }}
            className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 active:scale-90 transition-interaction"
            title="Delete skill"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
        <ChevronRight className="w-4 h-4 text-muted-foreground" />
        <Toggle enabled={!!skill.is_enabled} onToggle={() => onToggle(skill)} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skill Detail Panel
// ---------------------------------------------------------------------------

function SkillDetail({
  skill,
  onClose,
  onToggle,
  onDelete,
}: {
  skill: Skill;
  onClose: () => void;
  onToggle: (s: Skill) => void;
  onDelete: (s: Skill) => void;
}) {
  const taskTypes = parseTaskTypes(skill.task_types);
  const canDelete = skill.skill_type !== "public";

  return (
    <div className="w-1/2 flex flex-col">
      <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
        <h3 className="font-semibold text-[13px] tracking-tight">{skill.name}</h3>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/60 active:scale-95 transition-interaction"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Type</label>
          <p className="text-[13px] mt-0.5">{skill.skill_type}</p>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Slash Command</label>
          <p className="text-[13px] mt-0.5 font-mono text-primary">/{skill.name}</p>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Description</label>
          <p className="text-[13px] mt-0.5">{skill.description || "No description"}</p>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">File Path</label>
          <p className="text-xs mt-0.5 font-mono break-all">{skill.file_path}</p>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Task Types</label>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {taskTypes.length > 0 ? (
              taskTypes.map((t) => (
                <span
                  key={t}
                  className="text-xs bg-secondary px-2 py-0.5 rounded-[var(--radius-sm)] text-muted-foreground"
                >
                  {t}
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">None</span>
            )}
          </div>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Status</label>
          <div className="flex items-center gap-2 mt-1">
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-[var(--radius-sm)]",
                skill.is_enabled
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "bg-secondary text-muted-foreground",
              )}
            >
              {skill.is_enabled ? "Enabled" : "Disabled"}
            </span>
            <button
              onClick={() => onToggle(skill)}
              className="text-xs text-primary hover:underline"
            >
              {skill.is_enabled ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Created</label>
          <p className="text-[13px] mt-0.5">{formatDate(skill.created_at)}</p>
        </div>
        <div>
          <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Updated</label>
          <p className="text-[13px] mt-0.5">{formatDate(skill.updated_at)}</p>
        </div>

        {canDelete && (
          <div className="pt-2 border-t border-border/60">
            <button
              onClick={() => onDelete(skill)}
              className="flex items-center gap-1.5 text-xs text-destructive hover:bg-destructive/10 rounded-md px-3 py-2 transition-interaction"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete Skill
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseTaskTypes(raw: string): string[] {
  try {
    return JSON.parse(raw) as string[];
  } catch {
    return [];
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
