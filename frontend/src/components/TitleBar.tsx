import { Minus, Square, X } from "lucide-react";
import { cn } from "@/lib/utils";

export default function TitleBar() {
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
      className="flex items-center justify-between h-10 bg-card border-b border-border px-4 select-none shrink-0"
    >
      <div data-tauri-drag-region className="flex items-center gap-2 flex-1">
        <span className="text-primary font-bold text-sm">Neo</span>
        <span className="text-muted-foreground text-xs">Personal Intelligence Agent</span>
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
        "inline-flex items-center justify-center w-10 h-10 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
