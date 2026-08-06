from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.main import app

engine = create_engine("sqlite+pysqlite:///:memory:")


def override_db():
    with Session(engine) as db:
        yield db


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def test_live_endpoint() -> None:
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_ready_endpoint_checks_database() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "available"
