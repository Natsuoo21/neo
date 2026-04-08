import { useEffect, useState } from "react";
import {
  Puzzle, Play, Square, RefreshCw, Globe, HardDrive,
  Plus, Loader2, X, Key, Wifi, WifiOff, Settings2,
} from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";
import PageHeader from "./ui/PageHeader";
import EmptyState from "./ui/EmptyState";
import type {
  Plugin,
  PluginListResult,
  PluginInstallResult,
  AddRemoteResult,
  TestConnectionResult,
  SetSecretResult,
} from "@/types/rpc";

type Tab = "plugins" | "mcp" | "manage";

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
  const [tab, setTab] = useState<Tab>("plugins");
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

  const localPlugins = plugins.filter((p) => p.transport === "stdio");
  const remotePlugins = plugins.filter((p) => p.transport !== "stdio");
  const connectedRemotes = remotePlugins.filter((p) => isActive(p.status));

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={Puzzle} title="Plugins & MCP" subtitle={`(${plugins.length})`}>
        <button
          onClick={loadPlugins}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-card border border-border/60 hover:bg-accent/60 active:scale-95 transition-interaction disabled:opacity-40"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </PageHeader>

      {/* Tab Bar */}
      <div className="flex items-center gap-1 px-6 pt-3 pb-1 border-b border-border/60">
        <button
          onClick={() => setTab("plugins")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md transition-all",
            tab === "plugins"
              ? "bg-primary/10 text-primary border-b-2 border-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
          )}
        >
          <HardDrive className="w-3.5 h-3.5" />
          Plugins
          {localPlugins.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground">
              {localPlugins.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab("mcp")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md transition-all",
            tab === "mcp"
              ? "bg-primary/10 text-primary border-b-2 border-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
          )}
        >
          <Wifi className="w-3.5 h-3.5" />
          MCP Connected
          {connectedRemotes.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-emerald-500/20 text-emerald-500">
              {connectedRemotes.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab("manage")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md transition-all",
            tab === "manage"
              ? "bg-primary/10 text-primary border-b-2 border-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
          )}
        >
          <Settings2 className="w-3.5 h-3.5" />
          Manage MCP
          {remotePlugins.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground">
              {remotePlugins.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {tab === "plugins" && (
          <PluginsTab
            plugins={localPlugins}
            onStart={handleStart}
            onStop={handleStop}
            onRefreshTools={handleRefreshTools}
          />
        )}
        {tab === "mcp" && (
          <McpConnectedTab
            plugins={connectedRemotes}
            onRefreshTools={handleRefreshTools}
            onStop={handleStop}
          />
        )}
        {tab === "manage" && (
          <ManageMcpTab
            plugins={remotePlugins}
            showAddRemote={showAddRemote}
            setShowAddRemote={setShowAddRemote}
            onStart={handleStart}
            onStop={handleStop}
            onRefreshTools={handleRefreshTools}
            onRemoveRemote={handleRemoveRemote}
            onReload={loadPlugins}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plugins Tab — local stdio plugins
// ---------------------------------------------------------------------------

function PluginsTab({
  plugins,
  onStart,
  onStop,
  onRefreshTools,
}: {
  plugins: Plugin[];
  onStart: (name: string) => Promise<void>;
  onStop: (name: string) => Promise<void>;
  onRefreshTools: (name: string) => Promise<void>;
}) {
  if (plugins.length === 0) {
    return (
      <EmptyState
        icon={Puzzle}
        title="No local plugins discovered"
        description="Place MCP plugins in ~/.neo/plugins/ with a descriptor.json"
      />
    );
  }

  return (
    <>
      {plugins.map((plugin, i) => (
        <PluginCard
          key={plugin.name}
          plugin={plugin}
          index={i}
          onStart={onStart}
          onStop={onStop}
          onRefreshTools={onRefreshTools}
        />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// MCP Connected Tab — active remote MCP servers
// ---------------------------------------------------------------------------

function McpConnectedTab({
  plugins,
  onRefreshTools,
  onStop,
}: {
  plugins: Plugin[];
  onRefreshTools: (name: string) => Promise<void>;
  onStop: (name: string) => Promise<void>;
}) {
  if (plugins.length === 0) {
    return (
      <EmptyState
        icon={WifiOff}
        title="No MCP servers connected"
        description="Go to the Manage MCP tab to add and connect remote MCP servers"
      />
    );
  }

  return (
    <>
      {plugins.map((plugin, i) => (
        <PluginCard
          key={plugin.name}
          plugin={plugin}
          index={i}
          onRefreshTools={onRefreshTools}
          onStop={onStop}
          compact
        />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Manage MCP Tab — all remote servers + add remote + API key config
// ---------------------------------------------------------------------------

function ManageMcpTab({
  plugins,
  showAddRemote,
  setShowAddRemote,
  onStart,
  onStop,
  onRefreshTools,
  onRemoveRemote,
  onReload,
}: {
  plugins: Plugin[];
  showAddRemote: boolean;
  setShowAddRemote: (v: boolean) => void;
  onStart: (name: string) => Promise<void>;
  onStop: (name: string) => Promise<void>;
  onRefreshTools: (name: string) => Promise<void>;
  onRemoveRemote: (name: string) => Promise<void>;
  onReload: () => Promise<void>;
}) {
  return (
    <>
      {/* Add Remote button */}
      {!showAddRemote && (
        <button
          onClick={() => setShowAddRemote(true)}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 text-xs font-medium rounded-[10px] border border-dashed border-border/60 hover:border-primary/40 hover:bg-primary/5 text-muted-foreground hover:text-primary transition-all"
        >
          <Plus className="w-4 h-4" />
          Add Remote MCP Server
        </button>
      )}

      {showAddRemote && (
        <AddRemoteForm
          onClose={() => setShowAddRemote(false)}
          onAdded={() => {
            setShowAddRemote(false);
            onReload();
          }}
        />
      )}

      {plugins.length === 0 && !showAddRemote ? (
        <EmptyState
          icon={Globe}
          title="No remote MCP servers"
          description="Click 'Add Remote MCP Server' above to connect to external MCP servers"
        />
      ) : (
        plugins.map((plugin, i) => (
          <PluginCard
            key={plugin.name}
            plugin={plugin}
            index={i}
            onStart={onStart}
            onStop={onStop}
            onRefreshTools={onRefreshTools}
            onRemoveRemote={onRemoveRemote}
            showApiKey
            onReload={onReload}
          />
        ))
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Plugin Card — shared between all tabs
// ---------------------------------------------------------------------------

function PluginCard({
  plugin,
  index,
  compact,
  onStart,
  onStop,
  onRefreshTools,
  onRemoveRemote,
  showApiKey,
  onReload,
}: {
  plugin: Plugin;
  index: number;
  compact?: boolean;
  onStart?: (name: string) => Promise<void>;
  onStop?: (name: string) => Promise<void>;
  onRefreshTools?: (name: string) => Promise<void>;
  onRemoveRemote?: (name: string) => Promise<void>;
  showApiKey?: boolean;
  onReload?: () => Promise<void>;
}) {
  const style = getStatusStyle(plugin.status);
  const active = isActive(plugin.status);
  const isRemote = plugin.transport !== "stdio";

  return (
    <div
      className="rounded-[10px] border border-border/60 bg-card p-4 space-y-3 shadow-card animate-fade-in-up"
      style={{ animationDelay: `${index * 30}ms` }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            {isRemote ? (
              <Globe className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            ) : (
              <HardDrive className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
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
            <p className="text-[10px] text-muted-foreground mt-0.5 font-mono truncate max-w-[400px]">
              {plugin.url}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {active && onRefreshTools && (
            <button
              onClick={() => onRefreshTools(plugin.name)}
              className="p-1.5 rounded-md hover:bg-accent/60 text-muted-foreground active:scale-90 transition-interaction"
              title="Refresh tools"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          )}
          {!active && onStart && (
            <button
              onClick={() => onStart(plugin.name)}
              className="p-1.5 rounded-md hover:bg-accent/60 text-emerald-500 active:scale-90 transition-interaction"
              title="Start"
            >
              <Play className="w-4 h-4" />
            </button>
          )}
          {active && onStop && (
            <button
              onClick={() => onStop(plugin.name)}
              className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive active:scale-90 transition-interaction"
              title="Stop"
            >
              <Square className="w-4 h-4" />
            </button>
          )}
          {onRemoveRemote && (
            <button
              onClick={() => onRemoveRemote(plugin.name)}
              className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive active:scale-90 transition-interaction"
              title="Remove remote server"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Tools */}
      {plugin.tools.length > 0 && (
        <div className="border-t border-border/60 pt-2">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">
            Tools ({plugin.tools.length})
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

      {/* API Key section (Manage MCP tab only) */}
      {showApiKey && !compact && <ApiKeySection plugin={plugin} onReload={onReload} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// API Key Section — inline in plugin cards on the Manage MCP tab
// ---------------------------------------------------------------------------

function ApiKeySection({
  plugin,
  onReload,
}: {
  plugin: Plugin;
  onReload?: () => Promise<void>;
}) {
  const [tokenValue, setTokenValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Derive the token_env name from auth config or generate from plugin name
  const tokenEnv = (plugin as any).auth?.token_env || `${plugin.name.toUpperCase().replace(/-/g, "_")}_TOKEN`;

  const handleSaveKey = async () => {
    if (!tokenValue.trim()) return;
    setSaving(true);
    try {
      await rpc<SetSecretResult>("neo.plugin.set_secret", {
        name: tokenEnv,
        value: tokenValue.trim(),
      });
      setSaved(true);
      setTokenValue("");
      setTimeout(() => setSaved(false), 2500);
      if (onReload) await onReload();
    } catch (err) {
      console.error("Failed to save secret:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-t border-border/60 pt-2">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 flex items-center gap-1">
        <Key className="w-3 h-3" />
        API Key / Token
      </p>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground font-mono shrink-0">{tokenEnv}:</span>
        <input
          type="password"
          placeholder="Paste API key or token..."
          value={tokenValue}
          onChange={(e) => setTokenValue(e.target.value)}
          className="flex-1 px-2 py-1 text-xs rounded-md bg-background border border-border/60 focus:outline-none focus:ring-1 focus:ring-primary/50 font-mono"
        />
        <button
          onClick={handleSaveKey}
          disabled={!tokenValue.trim() || saving}
          className={cn(
            "flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-md active:scale-95 transition-interaction disabled:opacity-40",
            saved
              ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
              : "bg-primary text-primary-foreground hover:bg-primary/90",
          )}
        >
          {saving ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : saved ? (
            "Saved!"
          ) : (
            "Save"
          )}
        </button>
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
  const [tokenValue, setTokenValue] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // If user provided a token value, save it first so the test can use it
      if (authType && tokenValue.trim() && tokenEnv.trim()) {
        await rpc<SetSecretResult>("neo.plugin.set_secret", {
          name: tokenEnv.trim(),
          value: tokenValue.trim(),
        });
      }
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
      // Save token if provided
      if (authType && tokenValue.trim() && tokenEnv.trim()) {
        await rpc<SetSecretResult>("neo.plugin.set_secret", {
          name: tokenEnv.trim(),
          value: tokenValue.trim(),
        });
      }
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

  // Auto-generate token_env from name
  const autoTokenEnv = name
    ? `${name.toUpperCase().replace(/[^A-Z0-9]/g, "_")}_TOKEN`
    : "";

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
          <>
            <input
              type="text"
              placeholder={`Env var name (e.g., ${autoTokenEnv || "GITHUB_TOKEN"})`}
              value={tokenEnv}
              onChange={(e) => setTokenEnv(e.target.value)}
              onFocus={() => { if (!tokenEnv && autoTokenEnv) setTokenEnv(autoTokenEnv); }}
              className={inputClass}
            />
            <input
              type="password"
              placeholder="Paste API key / token value (saved securely)"
              value={tokenValue}
              onChange={(e) => setTokenValue(e.target.value)}
              className={inputClass}
            />
          </>
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
