from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_frontend_origin_is_allowed() -> None:
    response = client.options(
        "/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
