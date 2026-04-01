import { useEffect, useMemo, useState } from "react";
import { Zap, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import PageHeader from "./ui/PageHeader";
import SearchInput from "./ui/SearchInput";
import Toggle from "./ui/Toggle";
import EmptyState from "./ui/EmptyState";
import type { Skill, SkillsListResult, SkillsToggleResult } from "@/types/rpc";

export default function SkillBrowser() {
  const skills = useNeoStore((s) => s.skills);
  const setSkills = useNeoStore((s) => s.setSkills);
  const [search, setSearch] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);

  useEffect(() => {
    rpc<SkillsListResult>("neo.skills.list")
      .then((res) => setSkills(res.skills))
      .catch(console.error);
  }, [setSkills]);

  const handleToggle = async (skill: Skill) => {
    const newEnabled = skill.is_enabled === 0;
    const previousSkills = [...skills];

    // Optimistic update
    setSkills(
      skills.map((s) =>
        s.name === skill.name ? { ...s, is_enabled: newEnabled ? 1 : 0 } : s,
      ),
    );

    // Update selected skill if it's the toggled one
    if (selectedSkill?.name === skill.name) {
      setSelectedSkill({ ...skill, is_enabled: newEnabled ? 1 : 0 });
    }

    try {
      await rpc<SkillsToggleResult>("neo.skills.toggle", {
        name: skill.name,
        enabled: newEnabled,
      });
    } catch (err) {
      // Rollback on failure
      setSkills(previousSkills);
      if (selectedSkill?.name === skill.name) {
        setSelectedSkill(skill);
      }
      console.error("Failed to toggle skill:", err);
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

        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {filtered.map((skill, i) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              selected={selectedSkill?.id === skill.id}
              onToggle={handleToggle}
              onSelect={() =>
                setSelectedSkill(selectedSkill?.id === skill.id ? null : skill)
              }
              index={i}
            />
          ))}
          {filtered.length === 0 && (
            <EmptyState icon={Zap} title="No skills found" description="Try a different search term." />
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedSkill && (
        <SkillDetail
          skill={selectedSkill}
          onClose={() => setSelectedSkill(null)}
          onToggle={handleToggle}
        />
      )}
    </div>
  );
}

function SkillCard({
  skill,
  selected,
  onToggle,
  onSelect,
  index,
}: {
  skill: Skill;
  selected: boolean;
  onToggle: (s: Skill) => void;
  onSelect: () => void;
  index: number;
}) {
  const taskTypes = parseTaskTypes(skill.task_types);

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

      <div className="flex items-center gap-2">
        <ChevronRight className="w-4 h-4 text-muted-foreground" />
        <Toggle enabled={!!skill.is_enabled} onToggle={() => onToggle(skill)} />
      </div>
    </div>
  );
}

function SkillDetail({
  skill,
  onClose,
  onToggle,
}: {
  skill: Skill;
  onClose: () => void;
  onToggle: (s: Skill) => void;
}) {
  const taskTypes = parseTaskTypes(skill.task_types);

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
      </div>
    </div>
  );
}

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
