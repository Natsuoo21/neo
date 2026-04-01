import { useEffect } from "react";
import {
  MessageSquare,
  Zap,
  Timer,
  ClipboardList,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore, type ViewId } from "@/stores/neoStore";
import type { ConversationListResult, ConversationLoadResult } from "@/types/rpc";
import type { ChatMessage } from "@/stores/neoStore";

const NAV_ITEMS: { id: ViewId; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "skills", label: "Skills", icon: Zap },
  { id: "automations", label: "Automations", icon: Timer },
  { id: "actions", label: "Action Log", icon: ClipboardList },
  { id: "settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const view = useNeoStore((s) => s.view);
  const setView = useNeoStore((s) => s.setView);
  const collapsed = useNeoStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useNeoStore((s) => s.toggleSidebar);
  const clearMessages = useNeoStore((s) => s.clearMessages);
  const connected = useNeoStore((s) => s.connected);
  const sessions = useNeoStore((s) => s.sessions);
  const setSessions = useNeoStore((s) => s.setSessions);
  const sessionId = useNeoStore((s) => s.sessionId);
  const setSessionId = useNeoStore((s) => s.setSessionId);
  const setMessages = useNeoStore((s) => s.setMessages);

  // Load sessions on mount and when connected
  useEffect(() => {
    if (!connected) return;
    rpc<ConversationListResult>("neo.conversation.list")
      .then((res) => setSessions(res.sessions))
      .catch(console.error);
  }, [connected, setSessions]);

  const loadSession = async (sid: string) => {
    try {
      const res = await rpc<ConversationLoadResult>("neo.conversation.load", {
        session_id: sid,
        limit: 100,
      });
      setSessionId(sid);
      const msgs: ChatMessage[] = res.messages.map((m) => ({
        id: String(m.id),
        role: m.role,
        content: m.content,
        model: m.model_used || undefined,
        timestamp: new Date(m.created_at).getTime(),
      }));
      setMessages(msgs);
      setView("chat");
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  };

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-card border-r border-border shrink-0 transition-all duration-200",
        collapsed ? "w-14" : "w-52",
      )}
    >
      {/* New Chat button */}
      <div className="p-2">
        <button
          onClick={() => {
            clearMessages();
            setView("chat");
          }}
          className={cn(
            "flex items-center gap-2 w-full rounded-lg px-3 py-2 text-sm",
            "bg-primary/10 text-primary hover:bg-primary/20 transition-colors",
            collapsed && "justify-center px-0",
          )}
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* Navigation */}
      <nav className="p-2 space-y-1">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={cn(
              "flex items-center gap-3 w-full rounded-lg px-3 py-2 text-sm transition-colors",
              view === id
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <Icon className="w-4 h-4 shrink-0" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      {/* Conversation history */}
      {!collapsed && sessions.length > 0 && (
        <div className="flex-1 overflow-y-auto border-t border-border">
          <div className="px-3 py-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
            Recent Chats
          </div>
          <div className="px-2 space-y-0.5">
            {sessions.slice(0, 20).map((s) => (
              <button
                key={s.session_id}
                onClick={() => loadSession(s.session_id)}
                className={cn(
                  "w-full text-left rounded-lg px-2 py-1.5 text-xs transition-colors truncate",
                  sessionId === s.session_id
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
                title={`${s.message_count} messages`}
              >
                <span className="block truncate">
                  {s.session_id.slice(0, 8)}...
                </span>
                <span className="block text-[10px] opacity-60">
                  {formatSessionTime(s.last_message_at)} · {s.message_count} msgs
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Spacer when collapsed or no sessions */}
      {(collapsed || sessions.length === 0) && <div className="flex-1" />}

      {/* Footer: collapse toggle + connection status */}
      <div className="p-2 border-t border-border space-y-2">
        {!collapsed && (
          <div className="flex items-center gap-2 px-3 py-1 text-xs text-muted-foreground">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                connected ? "bg-emerald-500" : "bg-destructive",
              )}
            />
            {connected ? "Connected" : "Offline"}
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="flex items-center justify-center w-full rounded-lg px-3 py-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
        >
          {collapsed ? (
            <PanelLeft className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>
      </div>
    </aside>
  );
}

function formatSessionTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);

    if (diffHours < 1) return "just now";
    if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return "yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}
