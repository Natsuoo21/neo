import { useEffect } from "react";
import TitleBar from "./TitleBar";
import Sidebar from "./Sidebar";
import ChatView from "./ChatView";
import SkillBrowser from "./SkillBrowser";
import AutomationManager from "./AutomationManager";
import PluginManager from "./PluginManager";
import ActionLog from "./ActionLog";
import SettingsPanel from "./SettingsPanel";
import ConfirmationDialog from "./ConfirmationDialog";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";

const VIEW_COMPONENTS = {
  chat: ChatView,
  skills: SkillBrowser,
  automations: AutomationManager,
  plugins: PluginManager,
  actions: ActionLog,
  settings: SettingsPanel,
} as const;

export default function AppLayout() {
  const view = useNeoStore((s) => s.view);
  const ViewComponent = VIEW_COMPONENTS[view];
  const mobileOpen = useNeoStore((s) => s.sidebarMobileOpen);
  const setMobileOpen = useNeoStore((s) => s.setSidebarMobileOpen);

  // Close mobile sidebar on window resize to desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setMobileOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [setMobileOpen]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TitleBar />
      <div className="flex flex-1 overflow-hidden relative">
        {/* Desktop/tablet sidebar — hidden on mobile */}
        <div className="hidden md:block">
          <Sidebar />
        </div>

        {/* Mobile sidebar overlay */}
        {mobileOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
              onClick={() => setMobileOpen(false)}
            />
            <div className={cn(
              "fixed inset-y-0 left-0 z-50 w-72 md:hidden",
              "animate-slide-in-left",
            )}>
              <Sidebar />
            </div>
          </>
        )}

        <main className="flex-1 overflow-hidden bg-background">
          <ViewComponent />
        </main>
      </div>
      <ConfirmationDialog />
    </div>
  );
}
