"""
Tests for the /health endpoint.
"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_200():
    """GET /health should return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_healthy():
    """GET /health should report status 'healthy' and identify the service."""
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "no-wrong-door"
