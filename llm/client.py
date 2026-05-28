import anthropic
from config import ANTHROPIC_API_KEY, LLM_MODEL

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
) -> anthropic.types.Message:
    kwargs = {
        "model": model or LLM_MODEL,
        "max_tokens": 1024,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    return _get_client().messages.create(**kwargs)


def extract_tool_input(response: anthropic.types.Message) -> dict:
    """Pull the input dict from the first tool_use block in a response."""
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("No tool_use block found in response")
