import { useEffect, useState } from "react";
import { Puzzle, Play, Square, RefreshCw, Globe, HardDrive, Plus, Loader2, X } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";
import PageHeader from "./ui/PageHeader";
import EmptyState from "./ui/EmptyState";
import type {
  PluginListResult,
  PluginInstallResult,
  AddRemoteResult,
  TestConnectionResult,
} from "@/types/rpc";

const STATUS_STYLES: Record<string, { bg: string; dot: string }> = {
  running: { bg: "bg-emerald-500/10 text-emerald-500", dot: "bg-emerald-500" },
  connected: { bg: "bg-emerald-500/10 text-emerald-500", dot: "bg-emerald-500" },
  connecting: { bg: "bg-amber-500/10 text-amber-500", dot: "bg-amber-500 animate-pulse" },
  stopped: { bg: "bg-muted text-muted-foreground", dot: "bg-muted-foreground" },
  disconnected: { bg: "bg-muted text-muted-foreground", dot: "bg-muted-foreground" },
  error: { bg: "bg-destructive/10 text-destructive", dot: "bg-destructive" },
};

function getStatusStyle(status: string) {
  return STATUS_STYLES[status] ?? STATUS_STYLES.stopped;
}

function isActive(status: string) {
  return status === "running" || status === "connected" || status === "connecting";
}

export default function PluginManager() {
  const plugins = useNeoStore((s) => s.plugins);
  const setPlugins = useNeoStore((s) => s.setPlugins);
  const connected = useNeoStore((s) => s.connected);
  const [loading, setLoading] = useState(false);
  const [showAddRemote, setShowAddRemote] = useState(false);

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

  const handleRefreshTools = async (name: string) => {
    try {
      await rpc("neo.plugin.refresh_tools", { name });
      await loadPlugins();
    } catch (err) {
      console.error("Failed to refresh tools:", err);
    }
  };

  const handleRemoveRemote = async (name: string) => {
    try {
      await rpc("neo.plugin.remove_remote", { name });
      await loadPlugins();
    } catch (err) {
      console.error("Failed to remove remote:", err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={Puzzle} title="Plugins" subtitle={`(${plugins.length})`}>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddRemote(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 active:scale-95 transition-interaction"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Remote
          </button>
          <button
            onClick={loadPlugins}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-card border border-border/60 hover:bg-accent/60 active:scale-95 transition-interaction disabled:opacity-40"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </PageHeader>

      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {showAddRemote && (
          <AddRemoteForm
            onClose={() => setShowAddRemote(false)}
            onAdded={() => {
              setShowAddRemote(false);
              loadPlugins();
            }}
          />
        )}

        {plugins.length === 0 && !showAddRemote ? (
          <EmptyState
            icon={Puzzle}
            title="No plugins discovered"
            description="Place MCP plugins in ~/.neo/plugins/ or add a remote server"
          />
        ) : (
          plugins.map((plugin, i) => {
            const style = getStatusStyle(plugin.status);
            const active = isActive(plugin.status);
            const isRemote = plugin.transport !== "stdio";

            return (
              <div
                key={plugin.name}
                className="rounded-[10px] border border-border/60 bg-card p-4 space-y-3 shadow-card animate-fade-in-up"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      {isRemote ? (
                        <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                      ) : (
                        <HardDrive className="w-3.5 h-3.5 text-muted-foreground" />
                      )}
                      <h3 className="font-medium text-[13px]">{plugin.name}</h3>
                      <span className="text-[10px] text-muted-foreground font-mono">v{plugin.version}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">{plugin.transport}</span>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]",
                          style.bg,
                        )}
                      >
                        <span className={cn("w-1.5 h-1.5 rounded-full", style.dot)} />
                        {plugin.status}
                      </span>
                    </div>
                    {plugin.description && (
                      <p className="text-xs text-muted-foreground mt-1">{plugin.description}</p>
                    )}
                    {plugin.url && (
                      <p className="text-[10px] text-muted-foreground mt-0.5 font-mono truncate max-w-[300px]">
                        {plugin.url}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {active && (
                      <button
                        onClick={() => handleRefreshTools(plugin.name)}
                        className="p-1.5 rounded-md hover:bg-accent/60 text-muted-foreground active:scale-90 transition-interaction"
                        title="Refresh tools"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {!active ? (
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
                    {isRemote && (
                      <button
                        onClick={() => handleRemoveRemote(plugin.name)}
                        className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive active:scale-90 transition-interaction"
                        title="Remove remote server"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

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
            );
          })
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Remote Server Form
// ---------------------------------------------------------------------------

function AddRemoteForm({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState<"streamable_http" | "sse">("streamable_http");
  const [authType, setAuthType] = useState<"" | "bearer" | "api_key">("");
  const [tokenEnv, setTokenEnv] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await rpc<TestConnectionResult>("neo.plugin.test_connection", {
        url,
        transport,
        auth: authType ? { type: authType, token_env: tokenEnv } : undefined,
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({ success: false, error: String(err) });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await rpc<AddRemoteResult>("neo.plugin.add_remote", {
        name,
        url,
        transport,
        auth: authType ? { type: authType, token_env: tokenEnv } : undefined,
      });
      onAdded();
    } catch (err) {
      console.error("Failed to add remote:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    "w-full px-3 py-1.5 text-xs rounded-md bg-background border border-border/60 focus:outline-none focus:ring-1 focus:ring-primary/50";

  return (
    <div className="rounded-[10px] border border-primary/30 bg-card p-4 space-y-3 shadow-card">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-[13px] flex items-center gap-2">
          <Globe className="w-4 h-4" />
          Add Remote MCP Server
        </h3>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-accent/60">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-2">
        <input
          type="text"
          placeholder="Server name (e.g., github-mcp)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
        <input
          type="text"
          placeholder="URL (e.g., https://api.example.com/mcp)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className={inputClass}
        />
        <div className="flex gap-2">
          <select
            value={transport}
            onChange={(e) => setTransport(e.target.value as "streamable_http" | "sse")}
            className={cn(inputClass, "w-1/2")}
          >
            <option value="streamable_http">Streamable HTTP</option>
            <option value="sse">SSE (Legacy)</option>
          </select>
          <select
            value={authType}
            onChange={(e) => setAuthType(e.target.value as "" | "bearer" | "api_key")}
            className={cn(inputClass, "w-1/2")}
          >
            <option value="">No Auth</option>
            <option value="bearer">Bearer Token</option>
            <option value="api_key">API Key</option>
          </select>
        </div>
        {authType && (
          <input
            type="text"
            placeholder="Environment variable name (e.g., GITHUB_TOKEN)"
            value={tokenEnv}
            onChange={(e) => setTokenEnv(e.target.value)}
            className={inputClass}
          />
        )}
      </div>

      {testResult && (
        <div
          className={cn(
            "text-xs p-2 rounded-md",
            testResult.success ? "bg-emerald-500/10 text-emerald-600" : "bg-destructive/10 text-destructive",
          )}
        >
          {testResult.success
            ? `Connected! Found ${testResult.tools?.length ?? 0} tools.`
            : `Failed: ${testResult.error}`}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleTest}
          disabled={!url || testing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-card border border-border/60 hover:bg-accent/60 active:scale-95 transition-interaction disabled:opacity-40"
        >
          {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Test Connection
        </button>
        <button
          onClick={handleSubmit}
          disabled={!name || !url || submitting}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 active:scale-95 transition-interaction disabled:opacity-40"
        >
          {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Add Server
        </button>
      </div>
    </div>
  );
}
