from ....config import Settings
from ....logging import get_logger
from ....utils.enums import CallFinalState
from ..contracts import HandoffHumanRequest, HandoffHumanResponse
from ..mappings import TOOL_HANDOFF_HUMAN

log = get_logger()


async def handoff_human(
    args: dict,
    settings: Settings,
    call_id: str,
    tenant_id: str,
) -> tuple[dict, CallFinalState]:
    payload = HandoffHumanRequest(**args, call_id=call_id, to_number=None)
    log.info(
        "handoff_human",
        event_type="handoff",
        tenant_id=tenant_id,
        call_id=call_id,
        reason=payload.reason,
        tool_name=TOOL_HANDOFF_HUMAN,
        final_state=CallFinalState.TRANSFERIDA_HUMANO,
    )
    response = HandoffHumanResponse(
        status=CallFinalState.TRANSFERIDA_HUMANO,
        reason=payload.reason,
    )
    return response.model_dump(), CallFinalState.TRANSFERIDA_HUMANO
