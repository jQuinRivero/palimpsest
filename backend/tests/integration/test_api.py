"""End-to-end API tests over the real HTTP surface.

These exercise the full researcher journey: upload two witnesses, collate them,
read the result. Every payload returned by the API is checked against the
schema invariants, so a contract violation fails here rather than in a client.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.config import Settings, get_settings
from app.main import create_app
from app.models import ComparisonResult, check_comparison
from app.storage.sqlite_store import SqliteSessionStore

WITNESS_A = "It was the best of times.\n\nIt was the worst of times.\n"
WITNESS_B = "It was the brightest of times.\n\nIt was the worst of times.\n"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_path=str(tmp_path / "test.db"), version="test")
    store = SqliteSessionStore(str(tmp_path / "test.db"))

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    store.close()


def upload(client: TestClient, text: str, name: str = "witness.txt") -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": (name, text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


class TestMeta:
    def test_health(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_capabilities_lists_registered_parsers(self, client: TestClient) -> None:
        response = client.get("/api/v1/capabilities")
        assert response.status_code == 200
        body = response.json()

        names = {p["name"] for p in body["parsers"]}
        assert "plaintext" in names
        assert ".txt" in body["parsers"][0]["extensions"]
        assert body["max_upload_bytes"] > 0
        assert body["diff_options_defaults"]["granularity"] == "WORD"

    def test_capabilities_reports_ocr_flags(self, client: TestClient) -> None:
        """The OCR seam is visible in the contract before any OCR parser ships."""
        body = client.get("/api/v1/capabilities").json()
        for parser in body["parsers"]:
            assert parser["emits_confidence"] is False
            assert parser["is_async"] is False
            assert parser["requires_network"] is False

    def test_openapi_schema_is_served(self, client: TestClient) -> None:
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        assert "/api/v1/comparisons" in response.json()["paths"]


class TestDocuments:
    def test_upload_and_fetch(self, client: TestClient) -> None:
        document_id = upload(client, WITNESS_A)

        response = client.get(f"/api/v1/documents/{document_id}")
        assert response.status_code == 200
        body = response.json()

        assert body["source_format"] == "TXT"
        assert len(body["blocks"]) == 2
        assert body["metadata"]["word_count"] == 12
        assert body["blocks"][0]["confidence"] is None
        assert body["blocks"][0]["bbox"] is None

    def test_upload_honours_title(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("x.txt", WITNESS_A.encode(), "text/plain")},
            data={"title": "Crossing — draft 1"},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Crossing — draft 1"

    def test_empty_upload_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("empty.txt", b"   \n  ", "text/plain")},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "EMPTY_DOCUMENT"

    def test_unsupported_format_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("scan.tiff", b"II*\x00fake tiff", "image/tiff")},
        )
        assert response.status_code == 415
        assert response.json()["code"] == "UNSUPPORTED_FORMAT"

    def test_oversize_upload_rejected(self, client: TestClient, tmp_path: Path) -> None:
        settings = Settings(database_path=str(tmp_path / "t.db"), max_upload_bytes=64)
        client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]

        response = client.post(
            "/api/v1/documents",
            files={"file": ("big.txt", b"x " * 500, "text/plain")},
        )
        assert response.status_code == 413
        assert response.json()["code"] == "FILE_TOO_LARGE"

    def test_unknown_document(self, client: TestClient) -> None:
        response = client.get("/api/v1/documents/doc_missing")
        assert response.status_code == 404
        assert response.json()["code"] == "DOCUMENT_NOT_FOUND"

    def test_delete_is_idempotent(self, client: TestClient) -> None:
        document_id = upload(client, WITNESS_A)
        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert client.get(f"/api/v1/documents/{document_id}").status_code == 404

    def test_each_upload_gets_a_distinct_id(self, client: TestClient) -> None:
        """Two uploads must never collide, whatever the parser returns.

        Regression: the PDF parser once returned a constant document id, so the
        second PDF overwrote the first and a comparison of two different
        witnesses reported them as identical — the worst failure this tool can
        produce.
        """
        first = upload(client, WITNESS_A, "a.txt")
        second = upload(client, WITNESS_B, "b.txt")

        assert first != second
        assert (
            client.get(f"/api/v1/documents/{first}").json()["blocks"][0]["text"]
            != (client.get(f"/api/v1/documents/{second}").json()["blocks"][0]["text"])
        )

    def test_ids_are_unguessable(self, client: TestClient) -> None:
        """Unguessability is the entire access-control model in v1."""
        ids = {upload(client, WITNESS_A, f"w{n}.txt") for n in range(5)}
        assert len(ids) == 5
        for document_id in ids:
            assert document_id.startswith("doc_")
            # 128 bits of entropy, URL-safe base64, is at least 22 characters.
            assert len(document_id) >= 4 + 22

    def test_error_uses_problem_json(self, client: TestClient) -> None:
        response = client.get("/api/v1/documents/doc_missing")
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        for field in ("type", "title", "status", "detail", "code"):
            assert field in body


class TestComparisons:
    def test_full_journey(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")

        response = client.post(
            "/api/v1/comparisons",
            json={"a_document_id": a_id, "b_document_id": b_id},
        )
        assert response.status_code == 201, response.text

        result = ComparisonResult.model_validate(response.json())
        violations = check_comparison(result)
        assert not violations, "; ".join(violations)

        assert result.total_blocks == 2
        assert result.truncated is False
        assert result.metrics.insertions >= 1
        assert result.metrics.deletions >= 1
        assert result.a.id == a_id
        assert result.b.id == b_id

    def test_result_is_retrievable_and_valid(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")
        created = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        ).json()

        response = client.get(f"/api/v1/comparisons/{created['comparison_id']}")
        assert response.status_code == 200
        fetched = ComparisonResult.model_validate(response.json())
        assert not check_comparison(fetched)
        assert fetched.comparison_id == created["comparison_id"]

    def test_comparison_response_is_not_indexable(self, client: TestClient) -> None:
        """Unpublished scholarly material must never be crawled or cached."""
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")
        response = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        )
        assert "noindex" in response.headers["x-robots-tag"]
        assert "no-store" in response.headers["cache-control"]

    def test_include_blocks_false_marks_truncated(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")
        created = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        ).json()

        response = client.get(
            f"/api/v1/comparisons/{created['comparison_id']}",
            params={"include_blocks": "false"},
        )
        body = response.json()
        assert body["blocks"] == []
        assert body["truncated"] is True
        assert body["total_blocks"] == 2

    def test_block_paging(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")
        created = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        ).json()
        comparison_id = created["comparison_id"]

        page = client.get(
            f"/api/v1/comparisons/{comparison_id}/blocks",
            params={"offset": 0, "limit": 1},
        ).json()
        assert len(page["blocks"]) == 1
        assert page["total_blocks"] == 2
        assert page["offset"] == 0

        past_end = client.get(
            f"/api/v1/comparisons/{comparison_id}/blocks",
            params={"offset": 99, "limit": 10},
        ).json()
        assert past_end["blocks"] == []
        assert past_end["total_blocks"] == 2

    def test_identical_witnesses_report_no_change(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_A, "b.txt")
        result = ComparisonResult.model_validate(
            client.post(
                "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
            ).json()
        )
        assert not check_comparison(result)
        assert result.metrics.edit_count == 0
        assert result.metrics.similarity == 1.0

    def test_options_are_honoured_and_echoed(self, client: TestClient) -> None:
        a_id = upload(client, "The Cat Sat.", "a.txt")
        b_id = upload(client, "the cat sat.", "b.txt")
        result = ComparisonResult.model_validate(
            client.post(
                "/api/v1/comparisons",
                json={
                    "a_document_id": a_id,
                    "b_document_id": b_id,
                    "options": {"ignore_case": True},
                },
            ).json()
        )
        assert not check_comparison(result)
        assert result.options.ignore_case is True
        assert result.metrics.edit_count == 0

    def test_missing_document_rejected(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        response = client.post(
            "/api/v1/comparisons",
            json={"a_document_id": a_id, "b_document_id": "doc_nope"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "DOCUMENT_NOT_FOUND"

    def test_unknown_comparison(self, client: TestClient) -> None:
        response = client.get("/api/v1/comparisons/cmp_missing")
        assert response.status_code == 404
        assert response.json()["code"] == "COMPARISON_NOT_FOUND"

    def test_delete_comparison(self, client: TestClient) -> None:
        a_id = upload(client, WITNESS_A, "a.txt")
        b_id = upload(client, WITNESS_B, "b.txt")
        created = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        ).json()
        comparison_id = created["comparison_id"]

        assert client.delete(f"/api/v1/comparisons/{comparison_id}").status_code == 204
        assert client.get(f"/api/v1/comparisons/{comparison_id}").status_code == 404
