from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_frontend_origin_is_allowed() -> None:
    response = client.options(
        "/live",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        settings.frontend_origin
    )
