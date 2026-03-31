import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { ExecuteResult } from "@/types/rpc";

export default function FloatingBar() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [historyIdx, setHistoryIdx] = useState(-1);

  const loading = useNeoStore((s) => s.loading);
  const setLoading = useNeoStore((s) => s.setLoading);
  const lastResult = useNeoStore((s) => s.lastResult);
  const setLastResult = useNeoStore((s) => s.setLastResult);
  const commandHistory = useNeoStore((s) => s.commandHistory);
  const addToHistory = useNeoStore((s) => s.addToHistory);

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

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        dismiss();
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        handleSubmit();
        return;
      }

      // Command history navigation
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
    },
    [dismiss, handleSubmit, commandHistory, historyIdx],
  );

  return (
    <div className="h-screen flex items-center justify-center p-2">
      <div className="w-full max-w-[580px] bg-card/95 backdrop-blur-xl border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3">
          <div className="text-primary font-bold text-sm tracking-wide select-none">
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
            placeholder="Type a command..."
            disabled={loading}
            className="flex-1 bg-transparent border-none outline-none text-foreground placeholder:text-muted-foreground text-sm"
            autoComplete="off"
            spellCheck={false}
          />
          {loading && (
            <Loader2 className="w-4 h-4 text-primary animate-spin" />
          )}
        </div>

        {/* Result display */}
        {lastResult && (
          <div
            className={`px-4 py-2 border-t border-border text-xs truncate ${
              lastResult.status === "success"
                ? "text-emerald-400"
                : "text-destructive"
            }`}
          >
            {lastResult.message}
          </div>
        )}
      </div>
    </div>
  );
}
