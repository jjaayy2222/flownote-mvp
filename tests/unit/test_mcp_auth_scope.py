from types import SimpleNamespace

from backend.mcp.auth_scope import authenticated_user_hash
from backend.utils.common import mask_pii_id


def _context(request):
    return SimpleNamespace(
        request_context=SimpleNamespace(request=request),
    )


def test_authenticated_scope_comes_from_request_principal() -> None:
    principal = SimpleNamespace(identity="member@example.test", is_authenticated=True)
    request = SimpleNamespace(scope={"user": principal})

    assert authenticated_user_hash(_context(request)) == mask_pii_id(
        "member@example.test"
    )


def test_missing_or_unauthenticated_principal_fails_closed() -> None:
    assert authenticated_user_hash(_context(None)) is None
    request = SimpleNamespace(
        scope={
            "user": SimpleNamespace(
                identity="member@example.test", is_authenticated=False
            )
        }
    )

    assert authenticated_user_hash(_context(request)) is None
