import TitleBar from "./TitleBar";
import Sidebar from "./Sidebar";
import ChatView from "./ChatView";
import SkillBrowser from "./SkillBrowser";
import ActionLog from "./ActionLog";
import SettingsPanel from "./SettingsPanel";
import { useNeoStore } from "@/stores/neoStore";

const VIEW_COMPONENTS = {
  chat: ChatView,
  skills: SkillBrowser,
  actions: ActionLog,
  settings: SettingsPanel,
} as const;

export default function AppLayout() {
  const view = useNeoStore((s) => s.view);
  const ViewComponent = VIEW_COMPONENTS[view];

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TitleBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <ViewComponent />
        </main>
      </div>
    </div>
  );
}
