import {
  MessageSquare,
  Zap,
  ClipboardList,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useNeoStore, type ViewId } from "@/stores/neoStore";

const NAV_ITEMS: { id: ViewId; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "skills", label: "Skills", icon: Zap },
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
      <nav className="flex-1 p-2 space-y-1">
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
