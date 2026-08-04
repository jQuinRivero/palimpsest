"""The payload example in docs/05-data-schema.md must satisfy the real models.

This closes the loop between specification and implementation: the normative
example in the spec is parsed by the actual Pydantic models and checked by the
actual invariant code. If either drifts, this fails.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.models import ComparisonResult, check_comparison

DOCS = Path(__file__).resolve().parents[3] / "docs"
FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _comparison_payloads() -> list[tuple[str, dict[str, object]]]:
    found: list[tuple[str, dict[str, object]]] = []
    for md in sorted(DOCS.rglob("*.md")):
        for index, block in enumerate(FENCE.findall(md.read_text(encoding="utf-8")), start=1):
            payload = json.loads(block)
            if isinstance(payload, dict) and "comparison_id" in payload and payload.get("blocks"):
                found.append((f"{md.name}#{index}", payload))
    return found


PAYLOADS = _comparison_payloads()


def test_specification_contains_payload_examples() -> None:
    assert PAYLOADS, "no ComparisonResult examples found in docs/"


@pytest.mark.parametrize(("name", "payload"), PAYLOADS, ids=[n for n, _ in PAYLOADS])
def test_spec_example_parses_and_holds_invariants(name: str, payload: dict[str, object]) -> None:
    result = ComparisonResult.model_validate(payload)
    violations = check_comparison(result)
    assert not violations, f"{name}: " + "; ".join(violations)


@pytest.mark.parametrize(("name", "payload"), PAYLOADS, ids=[n for n, _ in PAYLOADS])
def test_spec_example_round_trips(name: str, payload: dict[str, object]) -> None:
    """Serialising our model must reproduce every field the spec example declares."""
    result = ComparisonResult.model_validate(payload)
    dumped = result.model_dump(mode="json")

    def compare(expected: object, actual: object, path: str) -> None:
        if isinstance(expected, dict):
            assert isinstance(actual, dict), f"{name}: {path} is not an object"
            for key, value in expected.items():
                assert key in actual, f"{name}: {path}.{key} missing after round trip"
                compare(value, actual[key], f"{path}.{key}")
        elif isinstance(expected, list):
            assert isinstance(actual, list), f"{name}: {path} is not an array"
            assert len(expected) == len(actual), f"{name}: {path} length changed"
            for i, value in enumerate(expected):
                compare(value, actual[i], f"{path}[{i}]")
        elif isinstance(expected, float) and isinstance(actual, float):
            assert abs(expected - actual) < 1e-9, f"{name}: {path} {expected} != {actual}"
        elif isinstance(expected, str) and path.endswith(("created_at", "expires_at")):
            pass  # datetime normalisation is expected
        else:
            assert expected == actual, f"{name}: {path} {expected!r} != {actual!r}"

    compare(payload, dumped, "$")
