"""Authenticated tenant scope extraction for MCP request handlers."""

from typing import Any, Optional

from backend.utils.common import mask_pii_id


def authenticated_user_hash(ctx: Any) -> Optional[str]:
    """Return the masked identity supplied by trusted HTTP authentication middleware."""
    request = ctx.request_context.request
    scope = getattr(request, "scope", None)
    principal = scope.get("user") if isinstance(scope, dict) else None
    identity = getattr(principal, "identity", None)
    if getattr(principal, "is_authenticated", False) is not True:
        return None
    if not isinstance(identity, str) or not identity.strip():
        return None
    return mask_pii_id(identity)
