TOOL_AUTHENTICATE_MEMBER = "authenticate_member"
TOOL_GET_AUTHORIZATION_STATUS = "get_authorization_status"
TOOL_SEARCH_PROVIDERS = "search_providers"
TOOL_HANDOFF_HUMAN = "handoff_human"


def mask_cpf(cpf: str) -> str:
    digits = "".join(filter(str.isdigit, cpf))
    return f"***{digits[-4:]}" if digits else "***"
