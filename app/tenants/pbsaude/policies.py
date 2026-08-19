from .mappings import TOOL_HANDOFF_HUMAN, TOOL_SEARCH_PROVIDERS

PBSAUDE_ENABLED_TOOLS = frozenset(
    {
        TOOL_SEARCH_PROVIDERS,
        TOOL_HANDOFF_HUMAN,
    }
)


def is_tool_enabled(tool_name: str) -> bool:
    return tool_name in PBSAUDE_ENABLED_TOOLS
