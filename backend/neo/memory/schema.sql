-- Neo — Personal Intelligence Agent
-- SQLite Schema v1.0
-- All tables created on first run via CREATE TABLE IF NOT EXISTS.

-- ============================================
-- user_profile: Who Neo serves.
-- Loaded into every LLM context window.
-- ============================================
CREATE TABLE IF NOT EXISTS user_profile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    role        TEXT,
    preferences TEXT,           -- JSON: writing_style, language, timezone
    tool_paths  TEXT,           -- JSON: obsidian_vault, downloads_dir, etc.
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- projects: Per-project memory and context.
-- ============================================
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    goals       TEXT,           -- JSON array
    stakeholders TEXT,          -- JSON array
    file_paths  TEXT,           -- JSON: key file locations
    conventions TEXT,           -- JSON: naming, formatting rules
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- action_log: Every action Neo takes.
-- Audit trail + pattern detection.
-- ============================================
CREATE TABLE IF NOT EXISTS action_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    input_text  TEXT NOT NULL,
    intent      TEXT,
    skill_used  TEXT,
    tool_used   TEXT,
    model_used  TEXT,           -- ollama / gemini / claude
    result      TEXT,           -- JSON: outcome details
    status      TEXT DEFAULT 'success',  -- success / error / cancelled
    duration_ms INTEGER,
    tokens_used INTEGER,
    cost_brl    REAL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- skills: Registry of available skills.
-- ============================================
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    file_path   TEXT NOT NULL,
    skill_type  TEXT NOT NULL,  -- 'public' or 'user'
    description TEXT,
    task_types  TEXT,           -- JSON array: what tasks trigger this skill
    is_enabled  INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- automations: Scheduled and event-driven tasks.
-- ============================================
CREATE TABLE IF NOT EXISTS automations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    trigger_type TEXT NOT NULL, -- 'schedule', 'file_event', 'startup', 'pattern'
    trigger_config TEXT,       -- JSON: cron expression, directory path, etc.
    command     TEXT NOT NULL,  -- The command Neo will execute
    is_enabled  INTEGER DEFAULT 1,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_run_at TEXT,
    last_status TEXT,          -- success / error / paused
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- conversations: Chat history for continuity.
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,  -- 'user' or 'assistant'
    content     TEXT NOT NULL,
    model_used  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- Indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_action_log_created ON action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_action_log_tool ON action_log(tool_used);
CREATE INDEX IF NOT EXISTS idx_action_log_status ON action_log(status);
CREATE INDEX IF NOT EXISTS idx_automations_trigger ON automations(trigger_type);
CREATE INDEX IF NOT EXISTS idx_automations_enabled ON automations(is_enabled);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_skills_type ON skills(skill_type);
