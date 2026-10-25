from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["knowledge_entries"] >= 1

def test_article_21_query_returns_source():
    response = client.post("/api/chat", json={"message": "Explain Article 21 and right to life"})
    assert response.status_code == 200
    body = response.json()
    assert "Article 21" in body["answer"]
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["url"].startswith("https://")
    assert "not legal advice" in body["disclaimer"]

def test_unknown_query_is_honest():
    response = client.post("/api/chat", json={"message": "What is the law about zorblyx?"})
    assert response.status_code == 200
    assert response.json()["confidence"] == "low"

def test_validation_rejects_too_short_message():
    response = client.post("/api/chat", json={"message": "x"})
    assert response.status_code == 422
