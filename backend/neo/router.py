"""Neo Complexity Router — Decides which LLM handles each request.

Routes: LOCAL (Ollama) | GEMINI (free tier) | CLAUDE (paid API)
"""


def route(command: str, token_count: int = 0) -> str:
    """Determine the optimal model tier for a given command.

    Returns: 'LOCAL', 'GEMINI', or 'CLAUDE'
    """
    # TODO: Implement in P1-E3
    return "CLAUDE"
