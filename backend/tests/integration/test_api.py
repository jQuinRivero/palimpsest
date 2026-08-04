"""End-to-end API tests over the real HTTP surface.

These exercise the full researcher journey: upload two witnesses, collate them,
read the result. Every payload returned by the API is checked against the
schema invariants, so a contract violation fails here rather than in a client.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.config import Settings, get_settings
from app.main import create_app
from app.models import ComparisonAccepted, ComparisonResult, DiffOptions, check_comparison
from app.models.identifiers import new_comparison_id
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
        test_client.app.state.store = store
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
    def test_over_inline_budget_returns_202_then_completes(self, client: TestClient) -> None:
        settings = Settings(
            database_path="unused.db",
            inline_blocks_per_comparison=1,
            max_blocks_per_comparison=10,
            rate_limit_enabled=False,
        )
        client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
        a_id = upload(client, "Alpha text.", "a.txt")
        b_id = upload(client, "Alpha revised text.", "b.txt")

        accepted_response = client.post(
            "/api/v1/comparisons",
            json={"a_document_id": a_id, "b_document_id": b_id},
        )
        assert accepted_response.status_code == 202, accepted_response.text
        assert accepted_response.headers["retry-after"] == "2"
        accepted = ComparisonAccepted.model_validate(accepted_response.json())

        fetched: ComparisonResult | None = None
        for _ in range(10):
            poll = client.get(f"/api/v1/comparisons/{accepted.comparison_id}")
            if poll.status_code == 200:
                fetched = ComparisonResult.model_validate(poll.json())
                break
            assert poll.status_code == 202
        assert fetched is not None
        assert not check_comparison(fetched)
        assert fetched.comparison_id == accepted.comparison_id

    def test_pending_comparison_polls_as_202(self, client: TestClient) -> None:
        a_id = upload(client, "Waiting A.", "a.txt")
        b_id = upload(client, "Waiting B.", "b.txt")
        store = client.app.state.store
        a = store.get_document(a_id)
        b = store.get_document(b_id)
        now = datetime.now(UTC)
        pending = store.put_pending_comparison(
            comparison_id=new_comparison_id(),
            a=a,
            b=b,
            options=DiffOptions(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        response = client.get(f"/api/v1/comparisons/{pending.comparison_id}")
        assert response.status_code == 202
        assert response.headers["retry-after"] == "2"
        body = ComparisonAccepted.model_validate(response.json())
        assert body.retry_after == 2
        assert body.comparison_id == pending.comparison_id

    def test_failed_background_comparison_surfaces_failure(self, client: TestClient) -> None:
        a_id = upload(client, "Failure A.", "a.txt")
        b_id = upload(client, "Failure B.", "b.txt")
        store = client.app.state.store
        a = store.get_document(a_id)
        b = store.get_document(b_id)
        now = datetime.now(UTC)
        pending = store.put_pending_comparison(
            comparison_id=new_comparison_id(),
            a=a,
            b=b,
            options=DiffOptions(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        store.mark_comparison_failed(pending.comparison_id, "boom")

        response = client.get(f"/api/v1/comparisons/{pending.comparison_id}")
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"
        assert "boom" in response.json()["detail"]

    def test_above_hard_ceiling_returns_budget_error(self, client: TestClient) -> None:
        settings = Settings(
            database_path="unused.db",
            max_blocks_per_comparison=1,
            rate_limit_enabled=False,
        )
        client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
        a_id = upload(client, "One.", "a.txt")
        b_id = upload(client, "Two.", "b.txt")

        response = client.post(
            "/api/v1/comparisons",
            json={"a_document_id": a_id, "b_document_id": b_id},
        )
        assert response.status_code == 413
        assert response.json()["code"] == "DIFF_BUDGET_EXCEEDED"

    def test_truncated_result_and_window_clamping(self, client: TestClient) -> None:
        settings = Settings(
            database_path="unused.db",
            comparison_window_block_threshold=1,
            default_block_page_limit=1,
            max_block_page_limit=2,
            rate_limit_enabled=False,
        )
        client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
        a_id = upload(client, "First.\n\nSecond.\n\nThird.", "a.txt")
        b_id = upload(client, "First changed.\n\nSecond.\n\nThird.", "b.txt")
        created = client.post(
            "/api/v1/comparisons", json={"a_document_id": a_id, "b_document_id": b_id}
        ).json()

        fetched_response = client.get(f"/api/v1/comparisons/{created['comparison_id']}")
        fetched = ComparisonResult.model_validate(fetched_response.json())
        assert not check_comparison(fetched)
        assert fetched.truncated is True
        assert fetched.total_blocks == 3
        assert len(fetched.blocks) == 1

        first_page = client.get(
            f"/api/v1/comparisons/{created['comparison_id']}/blocks",
            params={"offset": 0, "limit": 2},
        ).json()
        assert len(first_page["blocks"]) == 2
        assert first_page["limit"] == 2
        assert first_page["total_blocks"] == 3
        clamped = client.get(
            f"/api/v1/comparisons/{created['comparison_id']}/blocks",
            params={"offset": 0, "limit": 99},
        ).json()
        assert clamped["limit"] == 2
        past_end = client.get(
            f"/api/v1/comparisons/{created['comparison_id']}/blocks",
            params={"offset": 99, "limit": 2},
        ).json()
        assert past_end["blocks"] == []

    def test_rate_limiter_returns_retry_after(self, client: TestClient) -> None:
        settings = Settings(
            database_path="unused.db",
            rate_limit_requests_per_minute=0,
            rate_limit_burst=1,
        )
        client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]

        assert client.get("/api/v1/comparisons/cmp_missing").status_code == 404
        limited = client.get("/api/v1/comparisons/cmp_missing")
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "60"
        assert limited.json()["code"] == "RATE_LIMITED"

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
