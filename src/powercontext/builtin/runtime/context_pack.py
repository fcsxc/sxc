# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Canonical Context Pack wire format and prefix-reusing deltas."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512


class ContextPackError(ValueError):
    """Report a malformed pack, delta, chunk, or reconstruction."""


@dataclass(frozen=True, slots=True)
class ContextPack:
    """One complete context split into ordered UTF-8-safe chunks."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: Iterable[bytes], /) -> ContextPack:
        normalized = _normalize_items(items)
        digest = _pack_digest(normalized)
        byte_count = 0
        while True:
            raw = _canonical_json(_pack_payload(normalized, digest, byte_count))
            if len(raw) == byte_count:
                return cls(normalized, digest, byte_count)
            byte_count = len(raw)

    @classmethod
    def from_content(cls, content: str | bytes | None, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        if not isinstance(chunk_bytes, int) or isinstance(chunk_bytes, bool) or chunk_bytes < 1:
            raise ContextPackError("chunk_bytes must be a positive integer")  # noqa: TRY003
        if content is None:
            raw = b""
        elif isinstance(content, str):
            raw = content.encode("utf-8")
        elif isinstance(content, (bytes, bytearray, memoryview)):
            raw = bytes(content)
        else:
            raise ContextPackError("content must be text, bytes, or None")  # noqa: TRY003
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContextPackError("content must be valid UTF-8") from error  # noqa: TRY003
        chunks: list[bytes] = []
        current = bytearray()
        for character in text:
            encoded = character.encode("utf-8")
            if len(encoded) > chunk_bytes:
                raise ContextPackError("chunk limit cannot fit one UTF-8 character")  # noqa: TRY003
            if current and len(current) + len(encoded) > chunk_bytes:
                chunks.append(bytes(current))
                current.clear()
            current.extend(encoded)
        if current:
            chunks.append(bytes(current))
        return cls.build(chunks)

    def to_bytes(self) -> bytes:
        return _canonical_json(_pack_payload(self.items, self.digest, self.byte_count))

    @classmethod
    def from_bytes(cls, payload: bytes | bytearray | memoryview, /) -> ContextPack:
        raw = bytes(payload)
        value = _decode_json(raw)
        if not isinstance(value, dict) or set(value) != {"schema", "items", "digest", "byte_count"}:
            raise ContextPackError("pack must contain exactly schema, items, digest, and byte_count")  # noqa: TRY003
        if value["schema"] != PACK_SCHEMA:
            raise ContextPackError("unsupported pack schema")  # noqa: TRY003
        items = _decode_items(value["items"])
        digest = value["digest"]
        byte_count = value["byte_count"]
        if not isinstance(digest, str):
            raise ContextPackError("pack digest must be a string")  # noqa: TRY003
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise ContextPackError("pack byte_count must be a non-negative integer")  # noqa: TRY003
        if byte_count != len(raw):
            raise ContextPackError("pack byte_count does not match serialized length")  # noqa: TRY003
        if digest != _pack_digest(items):
            raise ContextPackError("pack digest does not match its chunks")  # noqa: TRY003
        return cls(items, digest, byte_count)


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """A target pack expressed as a retained base prefix plus a new suffix."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack, /) -> ContextPackDelta:
        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("delta requires two ContextPack values")  # noqa: TRY003
        prefix = 0
        for left, right in zip(base.items, target.items, strict=False):
            if left != right:
                break
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=target.items[prefix:],
        )

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    def to_bytes(self) -> bytes:
        payload = {
            "schema": DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [_encode_item(item) for item in self.appended],
        }
        return _canonical_json(payload)

    @classmethod
    def from_bytes(cls, payload: bytes | bytearray | memoryview, /) -> ContextPackDelta:
        raw = bytes(payload)
        value = _decode_json(raw)
        expected = {"schema", "base_digest", "target_digest", "prefix_items", "appended"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ContextPackError("delta must contain exactly its five wire fields")  # noqa: TRY003
        if value["schema"] != DELTA_SCHEMA:
            raise ContextPackError("unsupported delta schema")  # noqa: TRY003
        base_digest = value["base_digest"]
        target_digest = value["target_digest"]
        prefix = value["prefix_items"]
        if not isinstance(base_digest, str) or not isinstance(target_digest, str):
            raise ContextPackError("delta digests must be strings")  # noqa: TRY003
        if not isinstance(prefix, int) or isinstance(prefix, bool) or prefix < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")  # noqa: TRY003
        appended = _decode_items(value["appended"])
        return cls(base_digest, target_digest, prefix, appended)


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta, /) -> ContextPack:
    """Validate the base and target digests and return the reconstructed pack."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("reconstruction requires a ContextPack and ContextPackDelta")  # noqa: TRY003
    if delta.base_digest != base.digest:
        raise ContextPackError("delta base digest does not match the supplied pack")  # noqa: TRY003
    if (
        not isinstance(delta.prefix_items, int)
        or isinstance(delta.prefix_items, bool)
        or delta.prefix_items < 0
        or delta.prefix_items > len(base.items)
    ):
        raise ContextPackError("prefix_items is outside the base pack")  # noqa: TRY003
    target = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("reconstructed target digest does not match the delta")  # noqa: TRY003
    return target


def _pack_payload(items: tuple[bytes, ...], digest: str, byte_count: int) -> dict[str, Any]:
    return {
        "schema": PACK_SCHEMA,
        "items": [_encode_item(item) for item in items],
        "digest": digest,
        "byte_count": byte_count,
    }


def _pack_digest(items: tuple[bytes, ...]) -> str:
    unsigned = {"schema": PACK_SCHEMA, "items": [_encode_item(item) for item in items]}
    return "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContextPackError("wire payload must be valid UTF-8 JSON") from error  # noqa: TRY003


def _encode_item(item: bytes) -> str:
    return base64.b64encode(item).decode("ascii")


def _decode_items(value: Any) -> tuple[bytes, ...]:
    if not isinstance(value, list):
        raise ContextPackError("wire items must be a list")  # noqa: TRY003
    items: list[bytes] = []
    for encoded in value:
        if not isinstance(encoded, str):
            raise ContextPackError("wire items must be Base64 strings")  # noqa: TRY003
        try:
            items.append(base64.b64decode(encoded, validate=True))
        except (binascii.Error, ValueError) as error:
            raise ContextPackError("wire item is not valid Base64") from error  # noqa: TRY003
    return tuple(items)


def _normalize_items(items: Iterable[bytes]) -> tuple[bytes, ...]:
    normalized: list[bytes] = []
    for item in items:
        if not isinstance(item, (bytes, bytearray, memoryview)):
            raise ContextPackError("pack items must be bytes")  # noqa: TRY003
        normalized.append(bytes(item))
    return tuple(normalized)


__all__ = [
    "DEFAULT_CHUNK_BYTES",
    "DELTA_SCHEMA",
    "PACK_SCHEMA",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
