import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_live():
    r = client.get("/api/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["commit"] == os.environ.get("GIT_SHA", "unknown")
    assert body["environment"] == os.environ["ENVIRONMENT"]
