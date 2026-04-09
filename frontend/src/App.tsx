import { useEffect, useState } from "react";
import FloatingBar from "@/components/FloatingBar";
import AppLayout from "@/components/AppLayout";
import { checkBackendHealth } from "@/lib/backend";
import { registerHotkeys } from "@/lib/hotkeys";
import { notify } from "@/lib/notifications";
import { connectStream, rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { ConversationListResult } from "@/types/rpc";

type WindowLabel = "main" | "floating-bar";

function App() {
  const [windowLabel, setWindowLabel] = useState<WindowLabel>("main");
  const setConnected = useNeoStore((s) => s.setConnected);
  const setSessions = useNeoStore((s) => s.setSessions);

  useEffect(() => {
    async function detectWindow() {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const label = getCurrentWindow().label as WindowLabel;
        setWindowLabel(label);
      } catch {
        setWindowLabel("main");
      }
    }
    detectWindow();
  }, []);

  // Check backend health on mount + periodic polling
  useEffect(() => {
    checkBackendHealth().then(setConnected);
    const interval = setInterval(async () => {
      setConnected(await checkBackendHealth());
    }, 10000);
    return () => clearInterval(interval);
  }, [setConnected]);

  // Register global hotkey — only from main window to avoid double registration
  useEffect(() => {
    if (windowLabel !== "main") return;

    registerHotkeys(async () => {
      try {
        const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
        const bar = await WebviewWindow.getByLabel("floating-bar");
        if (bar) {
          await bar.show();
          await bar.setFocus();
        }
      } catch (err) {
        console.warn("Hotkey handler error:", err);
      }
    });
  }, [windowLabel]);

  // SSE stream → desktop notifications (main window only to prevent duplicates)
  useEffect(() => {
    if (windowLabel !== "main") return;

    const disconnect = connectStream(async (event, data) => {
      const d = data as Record<string, unknown>;

      if (event === "automation_status") {
        const status = d.status as string | undefined;
        const name = (d.name as string) || "Automation";
        if (status === "success") {
          await notify("Neo — Automation Complete", `${name} finished successfully.`);
        } else if (status === "error") {
          await notify("Neo — Automation Error", `${name} failed: ${d.error || "unknown error"}`);
        } else if (status === "paused") {
          await notify("Neo — Automation Paused", `${name} was paused.`);
        }
      } else if (event === "confirmation_request") {
        await notify("Neo — Action Requires Confirmation", (d.message as string) || "Please review the pending action.");
        // Show main window so user can interact with ConfirmationDialog
        try {
          const { getCurrentWindow } = await import("@tauri-apps/api/window");
          const win = getCurrentWindow();
          await win.show();
          await win.setFocus();
        } catch {
          // Not in Tauri
        }
      } else if (event === "suggestion") {
        await notify("Neo — New Suggestion", (d.description as string) || "Neo has a suggestion for you.");
      } else if (event === "session_updated") {
        try {
          const res = await rpc<ConversationListResult>("neo.conversation.list");
          setSessions(res.sessions);
        } catch (err) {
          console.error("Failed to refresh sessions:", err);
        }
      }
    });

    return disconnect;
  }, [windowLabel, setSessions]);

  if (windowLabel === "floating-bar") {
    return <FloatingBar />;
  }

  return <AppLayout />;
}

export default App;
