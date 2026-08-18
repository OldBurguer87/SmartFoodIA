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


def test_legacy_olivia_api_is_not_public() -> None:
    public_paths = {
        route.path
        for route in app.routes
    }

    assert not any(
        path.startswith("/api/v1/olivia")
        for path in public_paths
    )


def test_mutating_http_routes_are_explicitly_classified() -> None:
    allowed = {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/carts"),
        ("POST", "/api/v1/carts/{cart_id}/items"),
        ("DELETE", "/api/v1/carts/{cart_id}/items"),
        ("PATCH", "/api/v1/carts/{cart_id}/items/{item_id}"),
        ("DELETE", "/api/v1/carts/{cart_id}/items/{item_id}"),
        ("POST", "/api/v1/catalog/modifier-groups"),
        ("POST", "/api/v1/catalog/modifiers"),
        ("POST", "/api/v1/channels/whatsapp/webhook"),
        ("POST", "/api/v1/customers/find-or-create"),
        ("POST", "/api/v1/customers/{customer_id}/addresses"),
        ("POST", "/api/v1/integrations/consumer/{store_slug}/orders/details"),
        ("POST", "/api/v1/integrations/consumer/{store_slug}/orders/status"),
        ("POST", "/api/v1/integrations/consumer/{store_slug}/orders/{order_id}/events"),
        ("POST", "/api/v1/integrations/consumer/{store_slug}/orders/{order_id}/status"),
        ("POST", "/api/v1/operations/conversations/{conversation_id}/release"),
        ("POST", "/api/v1/operations/conversations/{conversation_id}/reply"),
        ("POST", "/api/v1/operations/conversations/{conversation_id}/takeover"),
        ("POST", "/api/v1/operations/knowledge-gaps/{gap_id}/resolve"),
        ("POST", "/api/v1/operations/stores/{store_id}/catalog/import/consumer"),
        ("PUT", "/api/v1/operations/stores/{store_id}/commercial-rules"),
        ("PUT", "/api/v1/operations/stores/{store_id}/commercial-rules/hours/{weekday}"),
        ("POST", "/api/v1/operations/stores/{store_id}/commercial-rules/zones"),
        ("DELETE", "/api/v1/operations/stores/{store_id}/commercial-rules/zones/{zone_id}"),
        ("POST", "/api/v1/operations/stores/{store_id}/knowledge/search"),
        ("POST", "/api/v1/operations/stores/{store_id}/menu-pdf"),
        ("DELETE", "/api/v1/operations/stores/{store_id}/menu-pdf"),
        ("POST", "/api/v1/operations/tickets/{ticket_id}/assign"),
        ("POST", "/api/v1/operations/tickets/{ticket_id}/resolve"),
        ("POST", "/api/v1/orders/checkout/{cart_id}"),
        ("POST", "/api/v1/products"),
    }

    actual = set()

    for route in app.routes:
        path = getattr(route, "path", "")

        if not path.startswith("/api/"):
            continue

        for method in getattr(route, "methods", set()) or set():
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                actual.add((method, path))

    assert actual == allowed
