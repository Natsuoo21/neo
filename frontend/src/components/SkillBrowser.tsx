import { useEffect, useState } from "react";
import { Zap, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { Skill, SkillsListResult, SkillsToggleResult } from "@/types/rpc";

export default function SkillBrowser() {
  const skills = useNeoStore((s) => s.skills);
  const setSkills = useNeoStore((s) => s.setSkills);
  const [search, setSearch] = useState("");

  useEffect(() => {
    rpc<SkillsListResult>("neo.skills.list")
      .then((res) => setSkills(res.skills))
      .catch(console.error);
  }, [setSkills]);

  const handleToggle = async (skill: Skill) => {
    const newEnabled = skill.is_enabled === 0;
    try {
      await rpc<SkillsToggleResult>("neo.skills.toggle", {
        name: skill.name,
        enabled: newEnabled,
      });
      setSkills(
        skills.map((s) =>
          s.name === skill.name ? { ...s, is_enabled: newEnabled ? 1 : 0 } : s,
        ),
      );
    } catch (err) {
      console.error("Failed to toggle skill:", err);
    }
  };

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.description.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">Skills</h2>
          </div>
          <span className="text-xs text-muted-foreground">
            {skills.filter((s) => s.is_enabled).length}/{skills.length} enabled
          </span>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:border-primary/50 transition-colors placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {filtered.map((skill) => (
          <SkillCard key={skill.id} skill={skill} onToggle={handleToggle} />
        ))}
        {filtered.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-8">
            No skills found.
          </p>
        )}
      </div>
    </div>
  );
}

function SkillCard({
  skill,
  onToggle,
}: {
  skill: Skill;
  onToggle: (s: Skill) => void;
}) {
  const taskTypes = (() => {
    try {
      return JSON.parse(skill.task_types) as string[];
    } catch {
      return [];
    }
  })();

  return (
    <div className="flex items-start gap-4 bg-card border border-border rounded-xl p-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm">{skill.name}</span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full",
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
              className="text-[10px] bg-secondary px-1.5 py-0.5 rounded text-muted-foreground"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      {/* Toggle switch */}
      <button
        onClick={() => onToggle(skill)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors",
          skill.is_enabled ? "bg-primary" : "bg-secondary",
        )}
      >
        <span
          className={cn(
            "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5",
            skill.is_enabled ? "translate-x-4 ml-0.5" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}
