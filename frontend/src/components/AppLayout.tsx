import { useEffect } from "react";
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
    <div className="h-screen w-full relative bg-background flex text-on-surface">
      {/* TOPNAVBAR (Injected relative to Sidebar) */}
      <header className="flex justify-between items-center w-full px-12 py-6 ml-72 fixed top-4 z-40 bg-transparent">
        <div className="flex items-center gap-2">
          <span className="text-xl font-black tracking-tighter text-primary">Super agente</span>
        </div>
        <div className="flex items-center gap-6">
          <span className="material-symbols-outlined text-slate-400 hover:text-white transition-colors cursor-pointer" style={{fontVariationSettings: "'FILL' 1"}}>notifications</span>
          <div className="flex items-center gap-3 cursor-pointer group">
            <div className="w-10 h-10 rounded-full overflow-hidden border border-white/10 group-hover:border-primary transition-all">
              <img alt="User Avatar" className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCRtw2qYmwX9y1JEjUDLPO-dgK9Cf1Hrs6abiXt02uX77ilGSWEX8FTcaFNMT4mougUOqnIHXVUilgAkGe8mzjKM6A0KA_KMwptFR1_cJoHjX5anCQcSMFsBKL8LwiTEt2lcFJ-lVWimeI-7P8z2onecEu0o_tpn7HQLLlSLPvwwn9HOQTlhs3NDHvMp_tSMuxqTExMVSolXO0eB0WZaZxTyNIbLFLxZm0tOt26lWFugEBTFSE4ZNEjq86Dm2xR7nZU-oIqPIWyevsa" />
            </div>
          </div>
        </div>
      </header>

      {/* Sidebar */}
      <div className="hidden md:flex flex-col z-50 fixed left-0 top-6 bottom-6 bg-white/5 backdrop-blur-xl rounded-3xl m-6 w-72 shadow-[0_0_60px_-15px_rgba(189,157,255,0.08)] overflow-hidden border border-white/5">
        <Sidebar />
      </div>

        {/* Mobile sidebar overlay */}
        {mobileOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-background/80 backdrop-blur-md md:hidden transition-opacity"
              onClick={() => setMobileOpen(false)}
            />
            <div className={cn(
              "fixed inset-y-4 left-4 z-50 w-72 md:hidden rounded-2xl bg-card/80 backdrop-blur-xl border border-white/5 shadow-float overflow-hidden",
              "animate-slide-in-left",
            )}>
              <Sidebar />
            </div>
          </>
        )}

        {/* Main Canvas */}
        <main className="flex-1 ml-80 mr-6 mt-24 mb-6 relative bg-[#1a1a1c]/30 backdrop-blur-md rounded-3xl shadow-[0_0_80px_-20px_rgba(0,0,0,0.5)] border border-white/5 flex overflow-hidden">
          <ViewComponent />
        </main>
      <ConfirmationDialog />
    </div>
  );
}
