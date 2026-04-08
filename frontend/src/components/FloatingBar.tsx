import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { ExecuteResult, Skill } from "@/types/rpc";

interface SlashSuggestion {
  label: string;
  description: string;
}

export default function FloatingBar() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState(-1);
  const [skillCommands, setSkillCommands] = useState<SlashSuggestion[]>([]);

  const loading = useNeoStore((s) => s.loading);
  const setLoading = useNeoStore((s) => s.setLoading);
  const lastResult = useNeoStore((s) => s.lastResult);
  const setLastResult = useNeoStore((s) => s.setLastResult);
  const commandHistory = useNeoStore((s) => s.commandHistory);
  const addToHistory = useNeoStore((s) => s.addToHistory);

  // Fetch enabled skills on mount for slash command autocomplete
  useEffect(() => {
    rpc<Skill[]>("neo.skills.list")
      .then((skills) => {
        setSkillCommands(
          skills
            .filter((s) => s.enabled)
            .map((s) => ({ label: `/${s.name}`, description: s.description })),
        );
      })
      .catch(() => {
        // Skills not available — slash autocomplete disabled
      });
  }, []);

  // Filter suggestions: slash commands when input starts with "/", otherwise history
  const suggestions = useMemo(() => {
    const trimmed = input.trim();
    if (!trimmed || trimmed.length < 1) return [];

    // Slash command mode
    if (trimmed.startsWith("/")) {
      const prefix = trimmed.toLowerCase();
      return skillCommands
        .filter((s) => s.label.toLowerCase().startsWith(prefix) && s.label !== trimmed)
        .slice(0, 8);
    }

    // History mode (requires at least 2 chars)
    if (trimmed.length < 2) return [];
    const lower = trimmed.toLowerCase();
    return commandHistory
      .filter((cmd) => cmd.toLowerCase().includes(lower) && cmd !== input)
      .slice(0, 5)
      .map((cmd) => ({ label: cmd, description: "" }));
  }, [input, commandHistory, skillCommands]);

  // Show/hide suggestions
  useEffect(() => {
    setShowSuggestions(suggestions.length > 0);
    setSelectedSuggestion(-1);
  }, [suggestions]);

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Auto-dismiss result after 3 seconds
  useEffect(() => {
    if (!lastResult) return;
    const timer = setTimeout(async () => {
      setLastResult(null);
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        await getCurrentWindow().hide();
      } catch {
        // Not in Tauri
      }
    }, 3000);
    return () => clearTimeout(timer);
  }, [lastResult, setLastResult]);

  const dismiss = useCallback(async () => {
    setLastResult(null);
    setInput("");
    setShowSuggestions(false);
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().hide();
    } catch {
      // Not in Tauri
    }
  }, [setLastResult]);

  const handleSubmit = useCallback(async () => {
    const cmd = input.trim();
    if (!cmd || loading) return;

    addToHistory(cmd);
    setInput("");
    setShowSuggestions(false);
    setLoading(true);
    setLastResult(null);

    try {
      const result = await rpc<ExecuteResult>("neo.execute", { command: cmd });
      setLastResult(result);
    } catch (err) {
      setLastResult({
        status: "error",
        message: err instanceof Error ? err.message : "Connection failed",
        tool_used: "",
        tool_result: null,
        model_used: "",
        routed_tier: "",
        duration_ms: 0,
        session_id: "",
      });
    } finally {
      setLoading(false);
    }
  }, [input, loading, addToHistory, setLoading, setLastResult]);

  const applySuggestion = useCallback(
    (suggestion: SlashSuggestion) => {
      // Append a space for slash commands so the user can type the remainder
      const value = suggestion.label.startsWith("/")
        ? suggestion.label + " "
        : suggestion.label;
      setInput(value);
      setShowSuggestions(false);
      setSelectedSuggestion(-1);
      inputRef.current?.focus();
    },
    [],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (showSuggestions) {
          setShowSuggestions(false);
        } else {
          dismiss();
        }
        return;
      }

      // Navigate suggestions
      if (showSuggestions && suggestions.length > 0) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setSelectedSuggestion((prev) =>
            prev < suggestions.length - 1 ? prev + 1 : 0,
          );
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setSelectedSuggestion((prev) =>
            prev > 0 ? prev - 1 : suggestions.length - 1,
          );
          return;
        }
        if (e.key === "Tab" && selectedSuggestion >= 0) {
          e.preventDefault();
          applySuggestion(suggestions[selectedSuggestion]);
          return;
        }
      }

      if (e.key === "Enter") {
        e.preventDefault();
        if (showSuggestions && selectedSuggestion >= 0) {
          applySuggestion(suggestions[selectedSuggestion]);
        } else {
          handleSubmit();
        }
        return;
      }

      // Command history navigation (only when no suggestions shown)
      if (!showSuggestions) {
        if (e.key === "ArrowUp") {
          e.preventDefault();
          if (commandHistory.length === 0) return;
          const next = Math.min(historyIdx + 1, commandHistory.length - 1);
          setHistoryIdx(next);
          setInput(commandHistory[next]);
          return;
        }

        if (e.key === "ArrowDown") {
          e.preventDefault();
          if (historyIdx <= 0) {
            setHistoryIdx(-1);
            setInput("");
            return;
          }
          const next = historyIdx - 1;
          setHistoryIdx(next);
          setInput(commandHistory[next]);
        }
      }
    },
    [
      dismiss,
      handleSubmit,
      commandHistory,
      historyIdx,
      showSuggestions,
      suggestions,
      selectedSuggestion,
      applySuggestion,
    ],
  );

  return (
    <div className="h-screen flex items-center justify-center p-2">
      <div className="w-full max-w-[580px] bg-card/95 backdrop-blur-2xl border border-border/50 rounded-[14px] shadow-float overflow-hidden">
        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3">
          <div className="text-primary font-semibold text-[13px] tracking-tight select-none">
            Neo
          </div>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setHistoryIdx(-1);
            }}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              // Delay to allow click on suggestion
              setTimeout(() => setShowSuggestions(false), 200);
            }}
            placeholder="Type a command..."
            disabled={loading}
            className="flex-1 bg-transparent border-none outline-none text-foreground placeholder:text-muted-foreground/60 text-[15px]"
            autoComplete="off"
            spellCheck={false}
          />
          {loading && (
            <div className="flex gap-1 items-center">
              <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          )}
        </div>

        {/* Autocomplete suggestions */}
        {showSuggestions && (
          <div className="border-t border-border/50">
            {suggestions.map((suggestion, idx) => (
              <button
                key={suggestion.label}
                onClick={() => applySuggestion(suggestion)}
                className={cn(
                  "w-full text-left px-4 py-2 text-[13px] transition-interaction flex items-baseline gap-2",
                  idx === selectedSuggestion
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                <span>{suggestion.label}</span>
                {suggestion.description && (
                  <span className="text-[11px] text-muted-foreground/60 truncate">
                    {suggestion.description}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Result display */}
        {lastResult && (
          <div
            role="status"
            aria-live="polite"
            className={cn(
              "px-4 py-2 border-t border-border/50 text-xs truncate font-mono",
              lastResult.status === "success"
                ? "text-emerald-400"
                : "text-destructive",
            )}
          >
            {lastResult.message}
          </div>
        )}
      </div>
    </div>
  );
}
