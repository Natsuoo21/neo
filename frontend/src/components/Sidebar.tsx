import { useEffect, useRef, useState } from "react";
import { Pencil, Pin, Search, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore, type ViewId } from "@/stores/neoStore";
import type {
  ConversationListResult,
  ConversationLoadResult,
  ConversationSearchResult,
  ConversationSession,
} from "@/types/rpc";
import type { ChatMessage } from "@/stores/neoStore";

const NAV_ITEMS: { id: ViewId; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "chat" },
  { id: "skills", label: "Skills", icon: "bolt" },
  { id: "automations", label: "Automations", icon: "auto_mode" },
  { id: "plugins", label: "Plugins", icon: "extension" },
  { id: "actions", label: "Action Log", icon: "history_edu" },
  { id: "settings", label: "Settings", icon: "settings" },
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
  const updateSession = useNeoStore((s) => s.updateSession);
  const removeSession = useNeoStore((s) => s.removeSession);
  const sessionId = useNeoStore((s) => s.sessionId);
  const setSessionId = useNeoStore((s) => s.setSessionId);
  const setMessages = useNeoStore((s) => s.setMessages);
  const setSidebarMobileOpen = useNeoStore((s) => s.setSidebarMobileOpen);

  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const editInputRef = useRef<HTMLInputElement>(null);

  const closeMobile = () => setSidebarMobileOpen(false);

  // Load sessions on mount and when connected
  useEffect(() => {
    if (!connected) return;
    rpc<ConversationListResult>("neo.conversation.list")
      .then((res) => setSessions(res.sessions))
      .catch(console.error);
  }, [connected, setSessions]);

  // Debounced search: switch between list and search RPCs
  useEffect(() => {
    if (!connected) return;
    const timer = setTimeout(() => {
      const q = searchQuery.trim();
      if (!q) {
        rpc<ConversationListResult>("neo.conversation.list")
          .then((res) => setSessions(res.sessions))
          .catch(console.error);
      } else {
        rpc<ConversationSearchResult>("neo.conversation.search", { query: q })
          .then((res) => setSessions(res.sessions))
          .catch(console.error);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, connected, setSessions]);

  // Focus edit input when entering rename mode
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

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

  const startRename = (s: ConversationSession) => {
    setEditingId(s.session_id);
    setEditValue(s.title || s.first_user_message?.slice(0, 50) || "");
  };

  const commitRename = async (sid: string) => {
    const title = editValue.trim();
    setEditingId(null);
    if (!title) return;
    updateSession(sid, { title });
    try {
      await rpc("neo.conversation.rename", { session_id: sid, title });
    } catch (err) {
      console.error("Failed to rename session:", err);
      // Refetch on error to recover the real state
      rpc<ConversationListResult>("neo.conversation.list")
        .then((res) => setSessions(res.sessions))
        .catch(console.error);
    }
  };

  const handleDelete = async (s: ConversationSession) => {
    const label = s.title || s.first_user_message?.slice(0, 30) || "this chat";
    if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return;
    removeSession(s.session_id);
    if (sessionId === s.session_id) {
      clearMessages();
    }
    try {
      await rpc("neo.conversation.delete", { session_id: s.session_id });
    } catch (err) {
      console.error("Failed to delete session:", err);
      rpc<ConversationListResult>("neo.conversation.list")
        .then((res) => setSessions(res.sessions))
        .catch(console.error);
    }
  };

  const handlePin = async (s: ConversationSession) => {
    const newPinned = s.is_pinned ? 0 : 1;
    updateSession(s.session_id, {
      is_pinned: newPinned as 0 | 1,
      pinned_at: newPinned ? new Date().toISOString() : null,
    });
    try {
      await rpc("neo.conversation.pin", {
        session_id: s.session_id,
        pinned: Boolean(newPinned),
      });
      // Refetch to get authoritative sort order
      const res = await rpc<ConversationListResult>("neo.conversation.list");
      setSessions(res.sessions);
    } catch (err) {
      console.error("Failed to pin session:", err);
    }
  };

  // Split pinned vs non-pinned; group non-pinned by date
  const visibleSessions = sessions.slice(0, 30);
  const pinnedSessions = visibleSessions.filter((s) => s.is_pinned);
  const nonPinnedSessions = visibleSessions.filter((s) => !s.is_pinned);
  const groupedNonPinned = groupSessionsByDate(nonPinnedSessions);
  const groups: SessionGroup[] = pinnedSessions.length
    ? [{ label: "Pinned", sessions: pinnedSessions }, ...groupedNonPinned]
    : groupedNonPinned;

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-transparent shrink-0 transition-all duration-300 ease-in-out select-none",
        collapsed ? "w-14" : "w-full",
      )}
    >
      {/* Branding Header */}
      {!collapsed && (
        <div className="mb-8 px-4 mt-6">
          <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-primary to-primary-dim font-headline tracking-wider">
            NEO
          </h1>
        </div>
      )}
      {/* New Chat button */}
      <div className={cn("px-4", collapsed ? "px-2 mb-4" : "mb-8 w-full")}>
        <button
          onClick={() => {
            clearMessages();
            setView("chat");
            closeMobile();
          }}
          className={cn(
            "w-full bg-gradient-to-r from-primary to-primary-dim text-on-primary-fixed py-4 px-6 rounded-full font-bold flex items-center justify-center gap-3 shadow-lg scale-95 active:scale-90 transition-transform duration-300",
            collapsed && "px-0"
          )}
        >
          <span className="material-symbols-outlined font-bold">add</span>
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* Navigation */}
      <nav className={cn("flex flex-col gap-2 overflow-y-auto pr-2 custom-scrollbar", collapsed && "items-center px-1", !collapsed && "px-2")}>
        {NAV_ITEMS.map(({ id, label, icon: IconName }) => (
          <div
            key={id}
            onClick={() => { setView(id); closeMobile(); }}
            className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-full font-headline tracking-wider text-sm uppercase transition-all duration-300 cursor-pointer",
              view === id
                ? "bg-primary/10 text-primary shadow-[inset_0_0_0_1px_rgba(255,255,255,0.1)]"
                : "text-slate-400 opacity-70 hover:bg-white/10 hover:opacity-100",
              collapsed && "justify-center px-0 w-10 h-10"
            )}
          >
            <span className="material-symbols-outlined">{IconName}</span>
            {!collapsed && <span>{label}</span>}
          </div>
        ))}
        {!collapsed && <div className="h-px w-10/12 mx-auto bg-white/5 my-4"></div>}
      </nav>

      {/* Search input */}
      {!collapsed && (
        <div className="px-4 mb-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search chats…"
              className="w-full bg-surface-container-low/40 pl-9 pr-3 py-2 rounded-xl text-sm text-on-surface placeholder:text-slate-500 border border-white/5 outline-none focus:border-primary/40 transition-colors"
            />
          </div>
        </div>
      )}

      {/* Conversation history */}
      {!collapsed && groups.length > 0 && (
        <div className="flex-1 overflow-y-auto px-4 space-y-4 custom-scrollbar">
          {groups.map((group) => (
            <div key={group.label} className="space-y-2">
              <h3 className="text-[10px] font-bold text-slate-500 tracking-[0.2em] uppercase flex items-center gap-1">
                {group.label === "Pinned" && <Pin className="w-3 h-3" />}
                {group.label}
              </h3>
              <div className="space-y-1">
                {group.sessions.map((s) => {
                  const isEditing = editingId === s.session_id;
                  const displayTitle =
                    s.title ||
                    s.first_user_message?.slice(0, 50) ||
                    `Chat ${s.session_id.slice(0, 6)}`;
                  return (
                    <div
                      key={s.session_id}
                      onClick={() => !isEditing && loadSession(s.session_id)}
                      className={cn(
                        "p-3 rounded-2xl transition-colors cursor-pointer group relative",
                        sessionId === s.session_id
                          ? "bg-white/10"
                          : "bg-surface-container-low/40 hover:bg-white/5"
                      )}
                    >
                      {isEditing ? (
                        <input
                          ref={editInputRef}
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onBlur={() => commitRename(s.session_id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              commitRename(s.session_id);
                            } else if (e.key === "Escape") {
                              setEditingId(null);
                            }
                          }}
                          className="w-full bg-transparent text-sm font-headline tracking-wide text-on-surface outline-none border-b border-primary/40"
                        />
                      ) : (
                        <p className="text-sm font-headline tracking-wide text-on-surface-variant group-hover:text-on-surface transition-colors line-clamp-1 pr-16">
                          {displayTitle}
                        </p>
                      )}
                      <span className="text-[10px] text-slate-500 font-mono mt-1 block">
                        {formatSessionTime(s.last_message_at)}
                      </span>

                      {!isEditing && (
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5 bg-background/60 backdrop-blur-sm rounded-lg p-0.5">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handlePin(s);
                            }}
                            title={s.is_pinned ? "Unpin" : "Pin"}
                            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-primary transition-colors"
                          >
                            <Pin
                              className={cn(
                                "w-3 h-3",
                                s.is_pinned && "fill-primary text-primary"
                              )}
                            />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(s);
                            }}
                            title="Rename"
                            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-on-surface transition-colors"
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(s);
                            }}
                            title="Delete"
                            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-error transition-colors"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Spacer when collapsed or no sessions */}
      {(collapsed || groups.length === 0) && <div className="flex-1" />}

      {/* Footer: collapse toggle + connection status */}
      <div className="mt-auto pt-4 border-t border-white/5 flex items-center justify-between px-4 pb-2">
        {!collapsed && (
          <div className="flex items-center gap-3">
            <div className="relative">
              <span className="material-symbols-outlined text-secondary">sensors</span>
              <div className={cn(
                "absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-background",
                connected ? "bg-green-500" : "bg-error"
               )}></div>
            </div>
            <span className="text-xs font-bold tracking-widest text-slate-400 uppercase">
               {connected ? "Connected" : "Offline"}
            </span>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-full hover:bg-white/5 text-slate-400 transition-colors"
        >
          <span className="material-symbols-outlined">
             {collapsed ? "last_page" : "first_page"}
          </span>
        </button>
      </div>
    </aside>
  );
}

interface SessionGroup {
  label: string;
  sessions: ConversationSession[];
}

function groupSessionsByDate(sessions: ConversationSession[]): SessionGroup[] {
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
