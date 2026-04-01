/**
 * Zustand store — central state management for Neo desktop app.
 */

import { create } from "zustand";
import type {
  ActionLogEntry,
  Automation,
  ConfirmationRequest,
  ConversationSession,
  ExecuteResult,
  Plugin,
  Provider,
  Skill,
  Suggestion,
  UserProfile,
} from "@/types/rpc";

export type ViewId = "chat" | "skills" | "automations" | "actions" | "settings" | "plugins";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  tool?: string;
  duration?: number;
  timestamp: number;
}

interface NeoState {
  // Connection
  connected: boolean;
  setConnected: (v: boolean) => void;

  // Loading
  loading: boolean;
  setLoading: (v: boolean) => void;

  // Current view (main window)
  view: ViewId;
  setView: (v: ViewId) => void;

  // Floating bar
  barVisible: boolean;
  setBarVisible: (v: boolean) => void;
  toggleBar: () => void;

  // Command history (floating bar)
  commandHistory: string[];
  addToHistory: (cmd: string) => void;

  // Chat messages (current session)
  sessionId: string | null;
  messages: ChatMessage[];
  setSessionId: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  setMessages: (msgs: ChatMessage[]) => void;
  clearMessages: () => void;

  // Sessions list
  sessions: ConversationSession[];
  setSessions: (s: ConversationSession[]) => void;

  // Last execution result (floating bar)
  lastResult: ExecuteResult | null;
  setLastResult: (r: ExecuteResult | null) => void;

  // Skills
  skills: Skill[];
  setSkills: (s: Skill[]) => void;

  // Action log
  actions: ActionLogEntry[];
  setActions: (a: ActionLogEntry[]) => void;

  // Settings / profile
  profile: UserProfile | null;
  setProfile: (p: UserProfile | null) => void;

  // Providers
  providers: Provider[];
  setProviders: (p: Provider[]) => void;

  // Automations
  automations: Automation[];
  setAutomations: (a: Automation[]) => void;
  automationsPaused: boolean;
  setAutomationsPaused: (v: boolean) => void;
  pendingConfirmations: ConfirmationRequest[];
  setPendingConfirmations: (c: ConfirmationRequest[]) => void;
  addPendingConfirmation: (c: ConfirmationRequest) => void;
  removePendingConfirmation: (id: string) => void;

  // Plugins
  plugins: Plugin[];
  setPlugins: (p: Plugin[]) => void;

  // Suggestions
  suggestions: Suggestion[];
  setSuggestions: (s: Suggestion[]) => void;
  dismissSuggestion: (id: number) => void;

  // Voice
  voiceActive: boolean;
  setVoiceActive: (v: boolean) => void;

  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useNeoStore = create<NeoState>((set) => ({
  // Connection
  connected: false,
  setConnected: (v) => set({ connected: v }),

  // Loading
  loading: false,
  setLoading: (v) => set({ loading: v }),

  // View
  view: "chat",
  setView: (v) => set({ view: v }),

  // Floating bar
  barVisible: false,
  setBarVisible: (v) => set({ barVisible: v }),
  toggleBar: () => set((s) => ({ barVisible: !s.barVisible })),

  // Command history
  commandHistory: [],
  addToHistory: (cmd) =>
    set((s) => ({
      commandHistory: [cmd, ...s.commandHistory.filter((c) => c !== cmd)].slice(0, 50),
    })),

  // Chat
  sessionId: null,
  messages: [],
  setSessionId: (id) => set({ sessionId: id }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  clearMessages: () => set({ messages: [], sessionId: null }),

  // Sessions
  sessions: [],
  setSessions: (s) => set({ sessions: s }),

  // Result
  lastResult: null,
  setLastResult: (r) => set({ lastResult: r }),

  // Skills
  skills: [],
  setSkills: (s) => set({ skills: s }),

  // Actions
  actions: [],
  setActions: (a) => set({ actions: a }),

  // Profile
  profile: null,
  setProfile: (p) => set({ profile: p }),

  // Providers
  providers: [],
  setProviders: (p) => set({ providers: p }),

  // Automations
  automations: [],
  setAutomations: (a) => set({ automations: a }),
  automationsPaused: false,
  setAutomationsPaused: (v) => set({ automationsPaused: v }),
  pendingConfirmations: [],
  setPendingConfirmations: (c) => set({ pendingConfirmations: c }),
  addPendingConfirmation: (c) =>
    set((s) => ({ pendingConfirmations: [...s.pendingConfirmations, c] })),
  removePendingConfirmation: (id) =>
    set((s) => ({
      pendingConfirmations: s.pendingConfirmations.filter((c) => c.id !== id),
    })),

  // Plugins
  plugins: [],
  setPlugins: (p) => set({ plugins: p }),

  // Suggestions
  suggestions: [],
  setSuggestions: (s) => set({ suggestions: s }),
  dismissSuggestion: (id) =>
    set((s) => ({ suggestions: s.suggestions.filter((sg) => sg.id !== id) })),

  // Voice
  voiceActive: false,
  setVoiceActive: (v) => set({ voiceActive: v }),

  // Sidebar
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
