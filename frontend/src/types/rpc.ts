/** JSON-RPC 2.0 types for Neo server communication. */

export interface RpcRequest {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
  id: number | string;
}

export interface RpcResponse<T = unknown> {
  jsonrpc: "2.0";
  result?: T;
  error?: RpcError;
  id: number | string | null;
}

export interface RpcError {
  code: number;
  message: string;
  data?: unknown;
}

// --- RPC method result types ---

export interface HealthResult {
  status: string;
  providers: string[];
}

export interface ExecuteResult {
  status: "success" | "error";
  message: string;
  tool_used: string;
  tool_result: string | null;
  model_used: string;
  routed_tier: string;
  duration_ms: number;
  session_id: string;
}

export interface ConversationNewResult {
  session_id: string;
}

export interface ConversationSession {
  session_id: string;
  started_at: string;
  last_message_at: string;
  message_count: number;
}

export interface ConversationListResult {
  sessions: ConversationSession[];
}

export interface ConversationMessage {
  id: number;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  model_used: string;
  created_at: string;
}

export interface ConversationLoadResult {
  session_id: string;
  messages: ConversationMessage[];
}

export interface Skill {
  id: number;
  name: string;
  file_path: string;
  skill_type: "public" | "user" | "community";
  description: string;
  task_types: string;
  is_enabled: number;
  created_at: string;
  updated_at: string;
}

export interface SkillsListResult {
  skills: Skill[];
}

export interface SkillsToggleResult {
  updated: boolean;
  name: string;
  enabled: boolean;
}

export interface SkillsCreateResult {
  created: boolean;
  name: string;
  path: string;
}

export interface SkillsImportResult {
  imported: number;
  skills: { name: string; description: string }[];
}

export interface SkillsDeleteResult {
  deleted: boolean;
  name: string;
}

export interface SkillsFoldersResult {
  folders: string[];
}

export interface SkillsAddFolderResult {
  folders: string[];
  synced: number;
}

export interface SkillsRemoveFolderResult {
  folders: string[];
  synced: number;
}

export interface ActionLogEntry {
  id: number;
  input_text: string;
  intent: string;
  skill_used: string;
  tool_used: string;
  model_used: string;
  routed_tier: string;
  result: string;
  status: string;
  duration_ms: number;
  tokens_used: number;
  cost_brl: number;
  created_at: string;
}

export interface ActionsRecentResult {
  actions: ActionLogEntry[];
}

export interface UserProfile {
  id: number;
  name: string;
  role: string;
  preferences: Record<string, string>;
  tool_paths: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface SettingsGetResult {
  profile: UserProfile | null;
}

export interface SettingsUpdateResult {
  updated: boolean;
}

export interface Provider {
  tier: string;
  name: string;
}

export interface ProvidersListResult {
  providers: Provider[];
}

// --- Automation types ---

export interface Automation {
  id: number;
  name: string;
  trigger_type: "schedule" | "file_event" | "startup" | "pattern";
  trigger_config: string;
  command: string;
  is_enabled: number;
  retry_count: number;
  max_retries: number;
  last_run_at: string | null;
  last_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationListResult {
  automations: Automation[];
}

export interface AutomationCreateResult {
  automation: Automation;
}

export interface AutomationToggleResult {
  updated: boolean;
  id: number;
  enabled: boolean;
}

export interface AutomationDeleteResult {
  deleted: boolean;
  id: number;
}

export interface ConfirmationRequest {
  id: string;
  automation_id: number;
  action_description: string;
  timeout_s?: number;
}

export interface AutomationPauseResult {
  paused: boolean;
}

export interface PendingConfirmationsResult {
  confirmations: ConfirmationRequest[];
}

export interface AutomationRunResult {
  triggered: boolean;
  id: number;
  result?: ExecuteResult;
}

export interface StatsResult {
  stats: {
    total_requests: number;
    success_count: number;
    error_count: number;
    total_duration_ms: number;
    total_tokens: number;
    total_cost: number;
    model_breakdown: { model_used: string; count: number; tokens: number; cost: number }[];
    tool_breakdown: { tool_used: string; count: number }[];
    tier_breakdown: { routed_tier: string; count: number }[];
  };
}

export interface PatternsResult {
  patterns: {
    pattern: string;
    count: number;
    last_run: string;
    sample_input: string;
  }[];
}

// --- Plugin types ---

export interface Plugin {
  name: string;
  version: string;
  description: string;
  tools: { name: string; description?: string }[];
  status: "running" | "stopped";
}

export interface PluginListResult {
  plugins: Plugin[];
}

export interface PluginInstallResult {
  started: boolean;
  name: string;
}

export interface PluginRemoveResult {
  removed: boolean;
  name: string;
}

export interface PluginStatusResult {
  name: string;
  status: string;
  tools: { name: string; description?: string }[];
}

// --- Suggestion types ---

export interface Suggestion {
  id: number;
  pattern: string;
  message: string;
  count: number;
  sample_input: string;
  dismissed: number;
  accepted: number;
  created_at: string;
}

export interface SuggestionListResult {
  suggestions: Suggestion[];
}

// --- Voice types ---

export interface VoiceStatusResult {
  stt_active: boolean;
  tts_enabled: boolean;
  wake_word_active: boolean;
  stt: {
    model_loaded: boolean;
    model_name: string;
    recording: boolean;
    wake_word_active: boolean;
    language: string;
  };
  tts: {
    enabled: boolean;
    speaking: boolean;
    rate: number;
    volume: number;
    voice_id: string | null;
    queue_size: number;
  };
}
