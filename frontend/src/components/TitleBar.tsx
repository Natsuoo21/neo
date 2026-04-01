import { Menu, Minus, Square, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useNeoStore } from "@/stores/neoStore";

export default function TitleBar() {
  const mobileOpen = useNeoStore((s) => s.sidebarMobileOpen);
  const setMobileOpen = useNeoStore((s) => s.setSidebarMobileOpen);

  const handleMinimize = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().minimize();
    } catch {}
  };

  const handleMaximize = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const win = getCurrentWindow();
      if (await win.isMaximized()) {
        await win.unmaximize();
      } else {
        await win.maximize();
      }
    } catch {}
  };

  const handleClose = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().hide();
    } catch {}
  };

  return (
    <div
      data-tauri-drag-region
      className="flex items-center justify-between h-9 bg-gradient-to-b from-card to-background border-b border-border/60 px-4 select-none shrink-0"
    >
      <div data-tauri-drag-region className="flex items-center gap-2 flex-1">
        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden inline-flex items-center justify-center w-7 h-7 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground active:scale-95 transition-interaction -ml-1 mr-1"
          aria-label="Toggle menu"
        >
          <Menu className="w-4 h-4" />
        </button>

        <span className="text-primary font-semibold text-[13px] tracking-tight">Neo</span>
        <span className="text-muted-foreground/60 text-[11px] font-medium tracking-wide hidden sm:inline">Personal Intelligence Agent</span>
      </div>

      <div className="flex items-center">
        <WindowButton onClick={handleMinimize} aria-label="Minimize">
          <Minus className="w-3.5 h-3.5" />
        </WindowButton>
        <WindowButton onClick={handleMaximize} aria-label="Maximize">
          <Square className="w-3 h-3" />
        </WindowButton>
        <WindowButton
          onClick={handleClose}
          aria-label="Close"
          className="hover:bg-destructive hover:text-destructive-foreground"
        >
          <X className="w-3.5 h-3.5" />
        </WindowButton>
      </div>
    </div>
  );
}

function WindowButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center w-9 h-9 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground active:scale-95 transition-interaction",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
