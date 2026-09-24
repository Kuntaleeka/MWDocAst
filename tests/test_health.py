from fastapi.testclient import TestClient

from api.index import app


def test_health() -> None:
    res = TestClient(app).get("/api/py/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
