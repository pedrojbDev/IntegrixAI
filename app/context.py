import contextvars

import structlog


call_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("call_id", default=None)
tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)


def set_call_context(call_id: str | None, tenant_id: str | None) -> None:
    """Bind call and tenant ids into contextvars for logging."""
    data: dict[str, str] = {}
    if call_id:
        call_id_var.set(call_id)
        data["call_id"] = call_id
    if tenant_id:
        tenant_id_var.set(tenant_id)
        data["tenant_id"] = tenant_id
    if data:
        structlog.contextvars.bind_contextvars(**data)


def clear_call_context() -> None:
    call_id_var.set(None)
    tenant_id_var.set(None)
    structlog.contextvars.clear_contextvars()


def get_call_context() -> dict[str, str | None]:
    return {"call_id": call_id_var.get(), "tenant_id": tenant_id_var.get()}
