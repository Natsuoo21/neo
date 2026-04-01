import { useEffect, useState } from "react";
import { Puzzle, Play, Square, RefreshCw } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";
import PageHeader from "./ui/PageHeader";
import EmptyState from "./ui/EmptyState";
import type { PluginListResult, PluginInstallResult } from "@/types/rpc";

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      await rpc("neo.plugin.stop", { name });
      await loadPlugins();
    } catch (err) {
      console.error("Failed to stop plugin:", err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={Puzzle} title="Plugins" subtitle={`(${plugins.length})`}>
        <button
          onClick={loadPlugins}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-card border border-border/60 hover:bg-accent/60 active:scale-95 transition-interaction disabled:opacity-40"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </PageHeader>

      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {plugins.length === 0 ? (
          <EmptyState
            icon={Puzzle}
            title="No plugins discovered"
            description="Place MCP plugins in ~/.neo/plugins/"
          />
        ) : (
          plugins.map((plugin, i) => (
            <div
              key={plugin.name}
              className="rounded-[10px] border border-border/60 bg-card p-4 space-y-3 shadow-card animate-fade-in-up"
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-[13px]">{plugin.name}</h3>
                    <span className="text-[10px] text-muted-foreground font-mono">v{plugin.version}</span>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
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
                      className="p-1.5 rounded-md hover:bg-accent/60 text-emerald-500 active:scale-90 transition-interaction"
                      title="Start plugin"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStop(plugin.name)}
                      className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive active:scale-90 transition-interaction"
                      title="Stop plugin"
                    >
                      <Square className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Tools */}
              {plugin.tools.length > 0 && (
                <div className="border-t border-border/60 pt-2">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">
                    Tools
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {plugin.tools.map((tool) => (
                      <span
                        key={tool.name}
                        className="text-[11px] px-2 py-0.5 rounded-[var(--radius-sm)] bg-primary/5 text-primary border border-primary/10 font-mono"
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
