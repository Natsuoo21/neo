"""Tests for the complexity router — tier selection and override parsing."""

from neo.router import CLAUDE, GEMINI, LOCAL, route, strip_override


class TestLocalRouting:
    def test_rename_routes_local(self):
        assert route("rename file X to Y") == LOCAL

    def test_create_note_routes_local(self):
        assert route("create note about meeting") == LOCAL

    def test_move_file_routes_local(self):
        assert route("move file to folder") == LOCAL

    def test_delete_routes_local(self):
        assert route("delete the old backup") == LOCAL

    def test_copy_routes_local(self):
        assert route("copy this file to desktop") == LOCAL

    def test_organize_routes_local(self):
        assert route("organize my downloads folder") == LOCAL


class TestGeminiRouting:
    def test_summarize_routes_gemini(self):
        assert route("summarize this article") == GEMINI

    def test_research_routes_gemini(self):
        assert route("research AI trends 2025") == GEMINI

    def test_compare_routes_gemini(self):
        assert route("compare React vs Vue") == GEMINI

    def test_explain_routes_gemini(self):
        assert route("explain quantum computing") == GEMINI

    def test_translate_routes_gemini(self):
        assert route("translate this to Portuguese") == GEMINI

    def test_what_is_routes_gemini(self):
        assert route("what is machine learning?") == GEMINI


class TestClaudeRouting:
    def test_complex_task_routes_claude(self):
        assert route("write a strategy document for Q2") == CLAUDE

    def test_unknown_command_defaults_to_claude(self):
        assert route("do something unique and creative") == CLAUDE

    def test_default_is_claude(self):
        assert route("build a full project plan") == CLAUDE


class TestOverridePrefix:
    def test_override_claude(self):
        assert route("@claude rename file X") == CLAUDE

    def test_override_local(self):
        assert route("@local write a strategy") == LOCAL

    def test_override_gemini(self):
        assert route("@gemini create note") == GEMINI


class TestTokenCountHeuristic:
    def test_short_commands_route_local(self):
        assert route("hello there", token_count=100) == LOCAL

    def test_long_commands_route_claude(self):
        # No keyword match + high token count → Claude
        assert route("build a full project plan", token_count=2000) == CLAUDE

    def test_zero_token_count_ignored(self):
        # token_count=0 means "not estimated", skip heuristic
        assert route("build a full project plan", token_count=0) == CLAUDE


class TestStripOverride:
    def test_strips_claude_prefix(self):
        assert strip_override("@claude rename file") == "rename file"

    def test_strips_local_prefix(self):
        assert strip_override("@local write strategy") == "write strategy"

    def test_strips_gemini_prefix(self):
        assert strip_override("@gemini create note") == "create note"

    def test_no_prefix_unchanged(self):
        assert strip_override("just a normal command") == "just a normal command"

    def test_partial_prefix_unchanged(self):
        assert strip_override("@claud something") == "@claud something"
