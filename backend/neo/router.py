"""Neo Complexity Router — Decides which LLM handles each request.

Routes: LOCAL (Ollama) | GEMINI (free tier) | CLAUDE (paid API)

Routing strategy:
1. @model override prefix (e.g., "@claude rename file") → forced tier
2. Keyword-based fast routing for known task types
3. Token count heuristic for short commands
4. Default to Claude for complex/unknown tasks

Fallback chain: LOCAL → GEMINI → CLAUDE (if selected tier is unavailable)
"""

# Tier constants
LOCAL = "LOCAL"
GEMINI = "GEMINI"
CLAUDE = "CLAUDE"

# Fast-route keywords — no LLM needed to decide
_LOCAL_KEYWORDS = frozenset(
    {
        "rename",
        "move",
        "copy",
        "delete",
        "create note",
        "create_note",
        "organize",
        "sort",
        "clean",
        "archive",
        "folder",
    }
)

_GEMINI_KEYWORDS = frozenset(
    {
        "research",
        "summarize",
        "article",
        "search",
        "web",
        "news",
        "compare",
        "review",
        "synthesis",
        "analyze",
        "explain",
        "translate",
        "what is",
        "who is",
        "how does",
    }
)

_OVERRIDE_PREFIXES = ("@claude ", "@local ", "@gemini ")


def route(command: str, token_count: int = 0) -> str:
    """Determine the optimal model tier for a given command.

    Args:
        command: The user's raw command string.
        token_count: Estimated token count of the full context (optional).

    Returns:
        'LOCAL', 'GEMINI', or 'CLAUDE'
    """
    # 1. Check @model override prefix
    if command.startswith("@claude "):
        return CLAUDE
    if command.startswith("@local "):
        return LOCAL
    if command.startswith("@gemini "):
        return GEMINI

    # 2. Keyword-based fast routing (check GEMINI first — complex tasks take priority)
    lower = command.lower()
    if any(kw in lower for kw in _GEMINI_KEYWORDS):
        return GEMINI
    if any(kw in lower for kw in _LOCAL_KEYWORDS):
        return LOCAL

    # 3. Token count heuristic — short commands are simple, route locally
    if token_count > 0 and token_count < 500:
        return LOCAL

    # 4. Default to Claude for complex tasks
    return CLAUDE


def strip_override(command: str) -> str:
    """Remove @model prefix from command before processing."""
    for prefix in _OVERRIDE_PREFIXES:
        if command.startswith(prefix):
            return command[len(prefix) :]
    return command
