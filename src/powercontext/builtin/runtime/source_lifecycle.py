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

"""Persistent source-dependency lifecycle for Memory and Topic Memory."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.runtime.models import GetMemoryEntryRequest
from powercontext.builtin.sources import validate_scope_id
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import BuiltinRuntime

_TABLE = "pc_source_lifecycle"
_TOPIC_ACTIVE: dict[tuple[str, str], bool] = {}


class SourceLifecycleError(ValueError):
    """Report an invalid lifecycle graph, event, or resolution."""


class SourceLifecycleEvent(BaseModel):
    """One versioned availability event for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str
    reason: str
    revision: int = Field(ge=1)
    sequence: int = Field(ge=1)
    available: bool

    @field_validator("node_id", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise SourceLifecycleError("lifecycle text must not be blank")  # noqa: TRY003
        return value


class SourceLifecycleApplication:
    """Resolve one scope-bound lifecycle service."""

    def __init__(self, runtime: BuiltinRuntime) -> None:
        self._runtime = runtime

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycleApplication:
        return ScopedSourceLifecycleApplication(self._runtime, validate_scope_id(scope_id))


class ScopedSourceLifecycleApplication:
    """Maintain the dependency DAG and propagate availability to native projections."""

    def __init__(self, runtime: BuiltinRuntime, scope_id: str) -> None:
        self._runtime = runtime
        self.scope_id = scope_id
        self._lock = asyncio.Lock()

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int) -> None:
        if not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError("source registration requires a SourceRef")  # noqa: TRY003
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("source revision must be a positive integer")  # noqa: TRY003
        try:
            await self._runtime.records.for_scope(self.scope_id).get_source(
                source_ref.source_type, source_ref.source_id
            )
        except Exception as error:
            raise SourceLifecycleError("source reference is not readable") from error  # noqa: TRY003
        async with self._lock:
            state = await self._load()
            existing = state["nodes"].get(node_id)
            candidate = {
                "kind": "source",
                "ref": source_ref.model_dump(mode="json"),
                "revision": revision,
                "sequence": 0,
                "available": True,
                "active": True,
                "last_reason": None,
            }
            if existing is not None:
                if existing != candidate:
                    raise SourceLifecycleError("node registration conflicts with the existing binding")  # noqa: TRY003
                return
            state["nodes"][node_id] = candidate
            state["order"].append(node_id)
            await self._save(state)

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("memory registration requires a MemoryCitation")  # noqa: TRY003
        try:
            await self._runtime.memory.for_scope(self.scope_id).get(GetMemoryEntryRequest(citation=citation))
        except Exception as error:
            raise SourceLifecycleError("memory citation is not readable") from error  # noqa: TRY003
        await self._register_derived(node_id, "memory", citation.model_dump(mode="json"), parents, policy)

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        if not isinstance(artifact_ref, ArtifactRef):
            raise SourceLifecycleError("topic registration requires an ArtifactRef")  # noqa: TRY003
        try:
            await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                artifact_ref.family, artifact_ref.artifact_id, artifact_ref.revision
            )
        except Exception as error:
            raise SourceLifecycleError("topic artifact is not readable") from error  # noqa: TRY003
        await self._register_derived(node_id, "topic", artifact_ref.model_dump(mode="json"), parents, policy)

    async def _register_derived(
        self,
        node_id: str,
        kind: str,
        reference: dict[str, Any],
        parents: tuple[str, ...],
        policy: str,
    ) -> None:
        if policy not in {"all", "any"}:
            raise SourceLifecycleError("policy must be all or any")  # noqa: TRY003
        if not parents or len(set(parents)) != len(parents):
            raise SourceLifecycleError("derived nodes require distinct parents")  # noqa: TRY003
        async with self._lock:
            state = await self._load()
            if node_id in state["nodes"]:
                existing = state["nodes"][node_id]
                if (
                    existing["kind"] != kind
                    or existing["ref"] != reference
                    or tuple(existing["parents"]) != parents
                    or existing["policy"] != policy
                ):
                    raise SourceLifecycleError("node registration conflicts with the existing binding")  # noqa: TRY003
                return
            for parent in parents:
                if parent == node_id or parent not in state["nodes"]:
                    raise SourceLifecycleError("parent must be registered before its child")  # noqa: TRY003
            active = _derive_active(state, parents, policy)
            state["nodes"][node_id] = {
                "kind": kind,
                "ref": reference,
                "parents": list(parents),
                "policy": policy,
                "active": active,
            }
            state["order"].append(node_id)
            if kind == "memory":
                await self._sync_memory(node_id, reference, active)
            else:
                _set_topic_active(self.scope_id, reference, active)
            await self._save(state)

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("apply requires a SourceLifecycleEvent")  # noqa: TRY003
        async with self._lock:
            state = await self._load()
            node = state["nodes"].get(event.node_id)
            if node is None or node["kind"] != "source":
                raise SourceLifecycleError("event targets an unknown source")  # noqa: TRY003
            if event.revision != node["revision"]:
                raise SourceLifecycleError("event revision does not match the source")  # noqa: TRY003
            if event.sequence < node["sequence"]:
                raise SourceLifecycleError("event sequence moved backwards")  # noqa: TRY003
            if event.sequence == node["sequence"]:
                if event.available == node["available"] and event.reason == node["last_reason"]:
                    return sorted(node_id for node_id, value in state["nodes"].items() if _active(value))
                raise SourceLifecycleError("event sequence is already used by different content")  # noqa: TRY003
            node["sequence"] = event.sequence
            node["available"] = event.available
            node["last_reason"] = event.reason
            self._recompute(state)
            for node_id in state["order"]:
                candidate = state["nodes"][node_id]
                if candidate["kind"] == "memory":
                    await self._sync_memory(node_id, candidate["ref"], bool(candidate["active"]))
                elif candidate["kind"] == "topic":
                    _set_topic_active(self.scope_id, candidate["ref"], bool(candidate["active"]))
            await self._save(state)
            return sorted(node_id for node_id, value in state["nodes"].items() if _active(value))

    async def resolve(self, node_id: str, /, *, purpose: str):
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown lifecycle purpose")  # noqa: TRY003
        state = await self._load()
        node = state["nodes"].get(node_id)
        if node is None:
            raise SourceLifecycleError("unknown lifecycle node")  # noqa: TRY003
        if purpose == "generation" and not _active(node):
            raise SourceLifecycleError("node is not available for generation")  # noqa: TRY003
        return _decode_ref(node["kind"], node["ref"])

    async def _sync_memory(self, node_id: str, reference: dict[str, Any], active: bool) -> None:
        citation = MemoryCitation.model_validate(reference)
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            head = await service.head(citation.memory_ref.artifact_id)
            manifest_entry = next(
                (entry for entry in head.content.manifest.entries if entry.entry_id == citation.entry_id),
                None,
            )
            if manifest_entry is None:
                raise SourceLifecycleError("memory entry is missing from its head")  # noqa: TRY003
            if (manifest_entry.state == "active") == active:
                return
            entry = next((item for item in await service.entries(head) if item.entry_id == citation.entry_id), None)
            if entry is None:
                raise SourceLifecycleError("memory entry version is missing")  # noqa: TRY003
            if active:
                await service.reactivate(head, entries=(entry,), reason=f"source-lifecycle:{node_id}")
            else:
                await service.forget(head, entries=(entry,), reason=f"source-lifecycle:{node_id}")

    async def _load(self) -> dict[str, Any]:
        async with self._database().transaction() as connection:
            await connection.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} (scope_id VARCHAR(128) PRIMARY KEY, payload TEXT NOT NULL)"
            )
            raw = await connection.scalar(
                text(f"SELECT payload FROM {_TABLE} WHERE scope_id = :scope_id"),  # noqa: S608
                {"scope_id": self.scope_id},
            )
        if raw is None:
            return {"nodes": {}, "order": []}
        try:
            state = json.loads(str(raw))
        except json.JSONDecodeError as error:
            raise SourceLifecycleError("persisted lifecycle state is invalid") from error  # noqa: TRY003
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("nodes"), dict)
            or not isinstance(state.get("order"), list)
        ):
            raise SourceLifecycleError("persisted lifecycle state is invalid")  # noqa: TRY003
        for node in state["nodes"].values():
            if node.get("kind") == "topic":
                _set_topic_active(self.scope_id, node["ref"], bool(node.get("active")))
        return state

    async def _save(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
        async with self._database().transaction() as connection:
            await connection.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} (scope_id VARCHAR(128) PRIMARY KEY, payload TEXT NOT NULL)"
            )
            await connection.exec_driver_sql(
                f"INSERT OR REPLACE INTO {_TABLE} (scope_id, payload) VALUES (?, ?)",  # noqa: S608
                (self.scope_id, payload),
            )

    def _database(self):
        database = getattr(self._runtime._provider, "database", None)
        if database is None:
            raise SourceLifecycleError("runtime database is unavailable")  # noqa: TRY003
        return database

    @staticmethod
    def _recompute(state: dict[str, Any]) -> None:
        for node_id in state["order"]:
            node = state["nodes"][node_id]
            if node["kind"] == "source":
                node["active"] = bool(node["available"])
            else:
                node["active"] = _derive_active(state, tuple(node["parents"]), node["policy"])


def topic_is_active(scope_id: str, artifact_id: str, /) -> bool:
    """Return the in-process Topic projection status for one scope/artifact."""

    return _TOPIC_ACTIVE.get((scope_id, artifact_id), True)


def _set_topic_active(scope_id: str, reference: dict[str, Any], active: bool) -> None:
    artifact_id = reference.get("artifact_id")
    if isinstance(artifact_id, str):
        _TOPIC_ACTIVE[(scope_id, artifact_id)] = active


def _derive_active(state: dict[str, Any], parents: tuple[str, ...], policy: str) -> bool:
    values = [
        bool(state["nodes"][parent].get("active", state["nodes"][parent].get("available", False))) for parent in parents
    ]
    return all(values) if policy == "all" else any(values)


def _active(node: dict[str, Any]) -> bool:
    return bool(node.get("active") if node.get("kind") != "source" else node.get("available"))


def _decode_ref(kind: str, reference: dict[str, Any]):
    if kind == "source":
        return SourceRef.model_validate(reference)
    if kind == "memory":
        return MemoryCitation.model_validate(reference)
    return ArtifactRef.model_validate(reference)


__all__ = [
    "ScopedSourceLifecycleApplication",
    "SourceLifecycleApplication",
    "SourceLifecycleError",
    "SourceLifecycleEvent",
    "topic_is_active",
]
