import os

from fastapi.testclient import TestClient

from app.config import APP_VERSION
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == APP_VERSION
    assert body["commit"] == os.environ.get("GIT_SHA", "unknown")
    assert body["environment"] == os.environ["ENVIRONMENT"]


def test_root_redirects_to_docs():
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/api/docs"
