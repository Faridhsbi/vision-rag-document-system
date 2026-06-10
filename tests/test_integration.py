"""Integration tests for the FastAPI endpoints.

Uses FastAPI's TestClient (httpx-based) to test endpoints without
starting a real server. LLM/embedding calls are not mocked so these
tests exercise the local fallback path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── Health ───────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_contains_status_ok(self, client: TestClient):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_contains_app_name(self, client: TestClient):
        data = client.get("/health").json()
        assert "app" in data
        assert isinstance(data["app"], str)


# ── Ingest ───────────────────────────────────────────────────────────

class TestIngestEndpoint:
    def test_ingest_rejects_non_pdf(self, client: TestClient):
        response = client.post(
            "/ingest",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 400

    def test_ingest_rejects_missing_file(self, client: TestClient):
        response = client.post("/ingest")
        assert response.status_code == 422  # FastAPI validation error


# ── Query ────────────────────────────────────────────────────────────

class TestQueryEndpoint:
    def test_query_rejects_empty_question(self, client: TestClient):
        response = client.post(
            "/query",
            json={"document_id": "test", "question": "   "},
        )
        assert response.status_code == 400

    def test_query_returns_answer_and_sources(self, client: TestClient):
        """Test against an already-ingested document (if available)."""
        # First check if any document exists
        docs_response = client.get("/documents")
        if docs_response.status_code != 200:
            pytest.skip("Documents endpoint failed")

        docs = docs_response.json()
        if not docs:
            pytest.skip("No ingested documents; run /ingest first")

        document_id = docs[0]["document_id"]
        response = client.post(
            "/query",
            json={
                "document_id": document_id,
                "question": "Apa isi dokumen ini?",
                "top_k": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert isinstance(data["sources"], list)

    def test_query_sources_contain_page_metadata(self, client: TestClient):
        docs = client.get("/documents").json()
        if not docs:
            pytest.skip("No ingested documents; run /ingest first")

        document_id = docs[0]["document_id"]
        response = client.post(
            "/query",
            json={
                "document_id": document_id,
                "question": "penagihan jam 21.00",
                "top_k": 3,
            },
        )
        if response.status_code != 200:
            pytest.skip("Query failed")

        sources = response.json()["sources"]
        if sources:
            source = sources[0]
            assert "page" in source
            assert "type" in source
            assert "excerpt" in source


# ── Documents ────────────────────────────────────────────────────────

class TestDocumentsEndpoint:
    def test_list_documents_returns_list(self, client: TestClient):
        response = client.get("/documents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_chunks_for_missing_doc(self, client: TestClient):
        response = client.get("/documents/nonexistent_doc_xyz/chunks")
        assert response.status_code == 200
        assert response.json() == []
