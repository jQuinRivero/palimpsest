"""Golden-corpus regression tests for real prose comparisons.

Golden updates are review-gated: run this module with
``PALIMPSEST_UPDATE_GOLDEN=1`` to rewrite ``tests/golden/*.json``, inspect the
structural and token-level diff as a human, and commit the source fixture,
expected payload, and review rationale only when the change is a genuine
improvement. Golden files must never be updated merely to silence CI.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.models import DiffOptions, SourceFormat, check_comparison
from app.models.diff import ComparisonResult
from app.models.document import Document
from app.services.formatting.payload import build_comparison
from app.services.ingestion.normalize import normalize

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN = Path(__file__).resolve().parents[1] / "golden"
CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
TTL = timedelta(days=7)
UPDATE_GOLDEN = os.environ.get("PALIMPSEST_UPDATE_GOLDEN") == "1"


CASES = (
    pytest.param("identical", id="identical-witnesses"),
    pytest.param("substitution", id="word-substitution"),
    pytest.param("insertion", id="sentence-insertion"),
    pytest.param("deletion", id="sentence-deletion"),
    # Phase 1 positional alignment cannot detect paragraph splits. Pin the
    # current modified+inserted-block output here; phase 3 should change it to
    # a structural split with shared grouping.
    pytest.param("paragraph_split", id="paragraph-split-phase-1-positional"),
    pytest.param("unrelated", id="unrelated-texts"),
    pytest.param("unicode", id="unicode-punctuation"),
)


def _fixture_text(case: str, witness: str) -> str:
    return (FIXTURES / f"{case}_{witness}.txt").read_text(encoding="utf-8")


def _make_document(case: str, witness: str) -> Document:
    """Build a deterministic TXT Document through the shared normalizer."""
    return normalize(
        _fixture_text(case, witness),
        document_id=f"doc_golden_{case}_{witness}",
        title=f"Golden {case} {witness.upper()}",
        source_format=SourceFormat.TXT,
        parser_name="plaintext",
        parser_version="1",
        witness=witness,
    )


def _build(case: str) -> ComparisonResult:
    return build_comparison(
        _make_document(case, "a"),
        _make_document(case, "b"),
        DiffOptions(),
        ttl=TTL,
        comparison_id=f"cmp_golden_{case}",
        created_at=CREATED_AT,
    )


def _serialize(result: ComparisonResult) -> str:
    """Return the committed byte-stable payload representation."""
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


@pytest.mark.parametrize("case", CASES)
def test_golden_payload(case: str) -> None:
    result = _build(case)
    violations = check_comparison(result)
    assert not violations, "; ".join(violations)

    actual = _serialize(result)
    expected_path = GOLDEN / f"{case}.json"
    if UPDATE_GOLDEN:
        expected_path.write_text(actual, encoding="utf-8")

    assert expected_path.read_text(encoding="utf-8") == actual


def test_comparison_serialization_is_deterministic() -> None:
    first = _serialize(_build("substitution"))
    second = _serialize(_build("substitution"))

    assert first.encode("utf-8") == second.encode("utf-8")
