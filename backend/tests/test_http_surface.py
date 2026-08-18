from app.main import app


def test_legacy_conversations_api_is_not_public() -> None:
    public_paths = {
        route.path
        for route in app.routes
    }

    assert "/api/v1/conversations" not in public_paths

    assert not any(
        path.startswith("/api/v1/conversations/")
        for path in public_paths
    )
