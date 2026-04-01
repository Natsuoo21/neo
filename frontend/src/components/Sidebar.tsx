import { useEffect } from "react";
import {
  MessageSquare,
  Zap,
  Timer,
  ClipboardList,
  Settings,
  Puzzle,
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
  { id: "plugins", label: "Plugins", icon: Puzzle },
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
  const setSidebarMobileOpen = useNeoStore((s) => s.setSidebarMobileOpen);

  const closeMobile = () => setSidebarMobileOpen(false);

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
      closeMobile();
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  };

  // Group sessions by date
  const groupedSessions = groupSessionsByDate(sessions.slice(0, 20));

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-card/80 border-r border-border/60 shrink-0 transition-all duration-200 select-none",
        collapsed ? "w-14" : "w-60",
      )}
    >
      {/* New Chat button */}
      <div className="p-2.5">
        <button
          onClick={() => {
            clearMessages();
            setView("chat");
            closeMobile();
          }}
          className={cn(
            "flex items-center gap-2.5 w-full rounded-lg px-3.5 py-2.5 text-sm font-medium",
            "bg-primary text-primary-foreground hover:brightness-110 active:scale-[0.98] transition-interaction shadow-card",
            collapsed && "justify-center px-0",
          )}
        >
          <Plus className="w-4.5 h-4.5 shrink-0" />
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-2.5 space-y-0.5">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => { setView(id); closeMobile(); }}
            className={cn(
              "flex items-center gap-3.5 w-full rounded-lg px-3.5 py-2.5 text-sm transition-interaction relative",
              view === id
                ? "bg-accent text-foreground shadow-card before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-primary"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground active:scale-[0.98]",
              collapsed && "justify-center px-0",
            )}
          >
            <Icon className="w-5 h-5 shrink-0" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      {/* Conversation history */}
      {!collapsed && sessions.length > 0 && (
        <div className="flex-1 overflow-y-auto mt-2 border-t border-border/60">
          {groupedSessions.map((group) => (
            <div key={group.label}>
              <div className="px-4 pt-3 pb-1.5 text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider">
                {group.label}
              </div>
              <div className="px-2 space-y-0.5">
                {group.sessions.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => loadSession(s.session_id)}
                    className={cn(
                      "w-full text-left rounded-lg px-3 py-2 transition-interaction group",
                      sessionId === s.session_id
                        ? "bg-accent text-foreground shadow-card"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground active:scale-[0.98]",
                    )}
                    title={`${s.message_count} messages`}
                  >
                    <span className="block text-xs truncate leading-snug">
                      {s.preview || s.session_id.slice(0, 12) + "..."}
                    </span>
                    <span className="flex items-center gap-1.5 mt-0.5 text-[10px] opacity-50">
                      <span>{formatSessionTime(s.last_message_at)}</span>
                      <span>·</span>
                      <span>{s.message_count} msgs</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Spacer when collapsed or no sessions */}
      {(collapsed || sessions.length === 0) && <div className="flex-1" />}

      {/* Footer: collapse toggle + connection status */}
      <div className="p-2.5 border-t border-border/60 space-y-2">
        {!collapsed && (
          <div className="flex items-center gap-2.5 px-3 py-1.5 text-xs text-muted-foreground">
            <span
              className={cn(
                "w-2 h-2 rounded-full shrink-0",
                connected ? "bg-emerald-500" : "bg-destructive",
              )}
            />
            <span>{connected ? "Connected" : "Offline"}</span>
            <span className="ml-auto text-[10px] opacity-40 font-mono">v0.1</span>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="flex items-center justify-center w-full rounded-lg px-3 py-2 text-muted-foreground hover:bg-accent/60 hover:text-foreground active:scale-95 transition-interaction"
        >
          {collapsed ? (
            <PanelLeft className="w-4.5 h-4.5" />
          ) : (
            <PanelLeftClose className="w-4.5 h-4.5" />
          )}
        </button>
      </div>
    </aside>
  );
}

interface SessionGroup {
  label: string;
  sessions: Array<{ session_id: string; last_message_at: string; message_count: number; preview?: string }>;
}

function groupSessionsByDate(sessions: Array<{ session_id: string; last_message_at: string; message_count: number; preview?: string }>): SessionGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, SessionGroup> = {};
  const order = ["Today", "Yesterday", "This Week", "Older"];

  for (const s of sessions) {
    const d = new Date(s.last_message_at);
    let label: string;
    if (d >= today) label = "Today";
    else if (d >= yesterday) label = "Yesterday";
    else if (d >= weekAgo) label = "This Week";
    else label = "Older";

    if (!groups[label]) groups[label] = { label, sessions: [] };
    groups[label].sessions.push(s);
  }

  return order.filter((l) => groups[l]).map((l) => groups[l]);
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
