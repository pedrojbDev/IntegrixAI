from ..core.security.ops import require_ready_principal

require_ops_token = require_ready_principal
require_ops_token_with_query = require_ready_principal

__all__ = ["require_ops_token", "require_ops_token_with_query"]
