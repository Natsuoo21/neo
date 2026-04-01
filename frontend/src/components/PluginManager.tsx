import { useEffect, useState } from "react";
import { Puzzle, Play, Square, RefreshCw } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";
import type { PluginListResult, PluginInstallResult, PluginRemoveResult } from "@/types/rpc";

export default function PluginManager() {
  const plugins = useNeoStore((s) => s.plugins);
  const setPlugins = useNeoStore((s) => s.setPlugins);
  const connected = useNeoStore((s) => s.connected);
  const [loading, setLoading] = useState(false);

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const res = await rpc<PluginListResult>("neo.plugin.list");
      setPlugins(res.plugins);
    } catch (err) {
      console.error("Failed to load plugins:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (connected) loadPlugins();
  }, [connected]);

  const handleStart = async (name: string) => {
    try {
      await rpc<PluginInstallResult>("neo.plugin.install", { name });
      await loadPlugins();
    } catch (err) {
      console.error("Failed to start plugin:", err);
    }
  };

  const handleStop = async (name: string) => {
    try {
      await rpc<PluginRemoveResult>("neo.plugin.remove", { name });
      await loadPlugins();
    } catch (err) {
      console.error("Failed to stop plugin:", err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Puzzle className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold">Plugins</h2>
          <span className="text-xs text-muted-foreground">({plugins.length})</span>
        </div>
        <button
          onClick={loadPlugins}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-card border border-border hover:bg-accent/50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Plugin list */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {plugins.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-sm space-y-2">
            <Puzzle className="w-10 h-10 opacity-30" />
            <p>No plugins discovered.</p>
            <p className="text-xs">Place MCP plugins in ~/.neo/plugins/</p>
          </div>
        ) : (
          plugins.map((plugin) => (
            <div
              key={plugin.name}
              className="rounded-xl border border-border bg-card p-4 space-y-3"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-sm">{plugin.name}</h3>
                    <span className="text-[10px] text-muted-foreground">v{plugin.version}</span>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full",
                        plugin.status === "running"
                          ? "bg-emerald-500/10 text-emerald-500"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "w-1.5 h-1.5 rounded-full",
                          plugin.status === "running" ? "bg-emerald-500" : "bg-muted-foreground",
                        )}
                      />
                      {plugin.status}
                    </span>
                  </div>
                  {plugin.description && (
                    <p className="text-xs text-muted-foreground mt-1">{plugin.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {plugin.status === "stopped" ? (
                    <button
                      onClick={() => handleStart(plugin.name)}
                      className="p-1.5 rounded-lg hover:bg-accent/50 text-emerald-500 transition-colors"
                      title="Start plugin"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStop(plugin.name)}
                      className="p-1.5 rounded-lg hover:bg-accent/50 text-destructive transition-colors"
                      title="Stop plugin"
                    >
                      <Square className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Tools */}
              {plugin.tools.length > 0 && (
                <div className="border-t border-border pt-2">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                    Tools
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {plugin.tools.map((tool) => (
                      <span
                        key={tool.name}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-primary/5 text-primary border border-primary/10"
                        title={tool.description}
                      >
                        {tool.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
