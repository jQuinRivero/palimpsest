"""Identifier generation.

Document and comparison ids are randomly generated with at least 128 bits of
entropy, because unguessability is the entire access-control model in v1 —
there are no accounts. Block and diff-block ids are deterministic sequences
scoped to their parent, which is what lets golden-corpus tests compare whole
payloads after masking only the two random ids and the timestamps.

Formats are normative (docs/05-data-schema.md) but consumers must treat every
id as opaque and must never parse one to recover structure.
"""

from __future__ import annotations

import secrets

#: 16 bytes = 128 bits, URL-safe base64 without padding.
_ENTROPY_BYTES = 16


def new_document_id() -> str:
    return f"doc_{secrets.token_urlsafe(_ENTROPY_BYTES)}"


def new_comparison_id() -> str:
    return f"cmp_{secrets.token_urlsafe(_ENTROPY_BYTES)}"


def block_id(witness: str, index: int) -> str:
    """Deterministic block id. ``witness`` is ``"a"`` or ``"b"``."""
    if witness not in ("a", "b"):
        raise ValueError(f"witness must be 'a' or 'b', got {witness!r}")
    return f"blk_{witness}_{index:04d}"


def diff_block_id(sequence: int) -> str:
    return f"dbk_{sequence:04d}"


def group_id(sequence: int) -> str:
    return f"grp_{sequence:04d}"
