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

"""Capture the visible events of one selected Pi session branch.

A Pi v3 session is a JSONL tree. The selected leaf and its parent chain define
the history path; each visible record on that path becomes an immutable
``CAPTURED`` Source. The connector keeps a durable checkpoint so branches,
appends, restarts, and recoveries only submit events that were not imported
before.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, JsonValue, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_EVENT_SOURCE_VERSION = "1"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
PI_SESSION_CONNECTOR_VERSION = "1"


class PiSessionInput(BaseModel):
    """One complete Pi session JSONL document plus an optional selected leaf."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible Pi event with its complete original record."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    """Durable evidence for exactly one visible Pi event."""

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_source_identity(self) -> PiEventSource:
        if self.source_id != self.name:
            raise ValueError("source_id must equal the Source name identity")  # noqa: TRY003
        return self


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Parse a Pi v3 session and return the visible events from root to leaf."""

    return _parse_session(value.content, value.leaf_id).events


def _parse_session(content: bytes, leaf_id: str | None) -> _ParsedSession:
    records = _decode_records(content)
    session_id = _validate_header(records[0])
    by_id = _collect_records(records[1:])
    leaf = _select_leaf(records[1:], by_id, leaf_id)
    chain = _ancestor_chain(leaf, by_id)
    events = tuple(event for record in chain if (event := _event_from_record(session_id, record)) is not None)
    return _ParsedSession(session_id=session_id, events=events, by_id=by_id)


def _collect_records(
    records: list[dict[str, JsonValue]],
) -> dict[str, dict[str, JsonValue]]:
    by_id: dict[str, dict[str, JsonValue]] = {}
    known: set[str] = set()
    for record in records:
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Pi session records require a non-empty id")  # noqa: TRY003
        if event_id in known:
            raise ValueError(f"Pi session id {event_id!r} is duplicated")  # noqa: TRY003
        if "parentId" not in record:
            raise ValueError("Pi session records require parentId")  # noqa: TRY003
        parent_id = record["parentId"]
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id not in known):
            raise ValueError(f"Pi session parent {parent_id!r} is missing or not yet defined")  # noqa: TRY003
        known.add(event_id)
        by_id[event_id] = record
    return by_id


def _select_leaf(
    records: list[dict[str, JsonValue]],
    by_id: dict[str, dict[str, JsonValue]],
    leaf_id: str | None,
) -> dict[str, JsonValue]:
    if leaf_id is None:
        if not records:
            raise ValueError("Pi session has no selectable leaf")  # noqa: TRY003
        return records[-1]
    if leaf_id not in by_id:
        raise ValueError(f"Pi session leaf {leaf_id!r} does not exist")  # noqa: TRY003
    return by_id[leaf_id]


def _ancestor_chain(
    leaf: dict[str, JsonValue],
    by_id: dict[str, dict[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    chain: list[dict[str, JsonValue]] = []
    visited: set[str] = set()
    current = leaf
    while True:
        event_id = current["id"]
        if event_id in visited:
            raise ValueError("Pi session contains a parent cycle")  # noqa: TRY003
        visited.add(event_id)
        chain.append(current)
        parent_id = current.get("parentId")
        if parent_id is None:
            break
        current = by_id[parent_id]
    chain.reverse()
    return chain


@dataclass(frozen=True, slots=True)
class _ParsedSession:
    session_id: str
    events: tuple[PiEventInput, ...]
    by_id: dict[str, dict[str, JsonValue]]


def _decode_records(content: bytes) -> list[dict[str, JsonValue]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Pi session content must be strict UTF-8") from error  # noqa: TRY003
    records: list[dict[str, JsonValue]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("Pi session content is not valid JSONL") from error  # noqa: TRY003
        if not isinstance(value, dict):
            raise ValueError("Pi session records must be JSON objects")  # noqa: TRY003, TRY004
        records.append(value)
    if not records:
        raise ValueError("Pi session content must contain a session header")  # noqa: TRY003
    return records


def _validate_header(header: dict[str, JsonValue]) -> str:
    if header.get("type") != "session":
        raise ValueError("the first Pi record must be a session header")  # noqa: TRY003
    if header.get("version") != 3:
        raise ValueError("Pi session version must be 3")  # noqa: TRY003
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Pi session header requires a non-empty id")  # noqa: TRY003
    return session_id


def _event_from_record(session_id: str, record: dict[str, JsonValue]) -> PiEventInput | None:
    event_type = record.get("type")
    if not isinstance(event_type, str):
        return None
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        extracted = _message_body(message)
        if extracted is None:
            return None
        role, body = extracted
    elif event_type == "custom_message":
        body = _content_text(record.get("content"), allow_tool_calls=False)
        if not body:
            return None
        role = "custom"
    elif event_type in {"compaction", "branch_summary"}:
        summary = record.get("summary")
        if not isinstance(summary, str) or not summary:
            return None
        body = summary
        role = event_type
    else:
        return None
    return PiEventInput(
        session_id=session_id,
        event_id=record["id"],
        parent_id=record.get("parentId"),
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def _message_body(message: dict[str, JsonValue]) -> tuple[str, str] | None:
    role = message.get("role")
    if role in {"user", "assistant"}:
        body = _content_text(message.get("content"), allow_tool_calls=True)
    elif role == "toolResult":
        text = _content_text(message.get("content"), allow_tool_calls=False) or ""
        tool_name = message.get("toolName") or "unknown"
        tool_call_id = message.get("toolCallId") or ""
        body = f"[tool_result {tool_name} {tool_call_id}] {text}"
    elif role == "bashExecution":
        command = message.get("command") or ""
        output = message.get("output")
        if output is None:
            output = ""
        elif not isinstance(output, str):
            output = str(output)
        body = f"$ {command}\n{output}"
    else:
        return None
    if not body:
        return None
    return str(role), body


def _content_text(content: JsonValue, *, allow_tool_calls: bool) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        elif block_type == "toolCall" and allow_tool_calls:
            name = block.get("name", "")
            call_id = block.get("id", "")
            arguments = block.get("arguments")
            if arguments is None:
                arguments = {}
            parts.append(f"[tool_call {name} {call_id}] {_compact_json(arguments)}")
    if not parts:
        return None
    return "\n".join(parts)


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("Pi tool call arguments must be JSON serializable") from error  # noqa: TRY003


class PiEventSourceAdapter:
    """Resolve one visible event into its captured Source and read it back exactly."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = _event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


def _event_source_id(session_id: str, event_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")  # noqa: TRY003
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a non-empty string")  # noqa: TRY003
    source_id = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"pi event source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return source_id


class PiEventTextEvidenceProjection:
    """Expose the complete event text as standard textual evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


class PiSessionConnector:
    """Submit only the visible events that were not imported before."""

    name = PI_SESSION_CONNECTOR_NAME
    version = PI_SESSION_CONNECTOR_VERSION
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        parsed = _parse_session(self._path.read_bytes(), self._leaf_id)
        stored = _load_checkpoint(session.checkpoint)
        imported = stored.setdefault(parsed.session_id, {})

        # Validate every previously imported event that still exists in the file,
        # including events on other branches, before submitting anything new.
        for event_id, fingerprint in imported.items():
            record = parsed.by_id.get(event_id)
            if record is not None and _fingerprint(record) != fingerprint:
                raise ValueError(f"Pi event {event_id!r} was rewritten after import")  # noqa: TRY003

        pending: list[tuple[PiEventInput, str]] = []
        for event in parsed.events:
            fingerprint = _fingerprint(event.record)
            known = imported.get(event.event_id)
            if known is not None:
                if known != fingerprint:
                    raise ValueError(f"Pi event {event.event_id!r} was rewritten after import")  # noqa: TRY003
                continue
            pending.append((event, fingerprint))

        if not pending:
            return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint=session.checkpoint)

        for event, fingerprint in pending:
            await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            imported[event.event_id] = fingerprint
        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE,
            checkpoint={"version": 1, "sessions": stored},
        )


def _load_checkpoint(value: JsonValue | None) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Pi session checkpoint is not a version 1 object")  # noqa: TRY003
    sessions = value.get("sessions")
    if not isinstance(sessions, dict):
        raise ValueError("Pi session checkpoint must contain sessions")  # noqa: TRY003, TRY004
    loaded: dict[str, dict[str, str]] = {}
    for session_id, events in sessions.items():
        if not isinstance(session_id, str) or not isinstance(events, dict):
            raise ValueError("Pi session checkpoint has an invalid session entry")  # noqa: TRY003, TRY004
        loaded[session_id] = {
            event_id: fingerprint
            for event_id, fingerprint in events.items()
            if isinstance(event_id, str) and isinstance(fingerprint, str)
        }
    return loaded


def _fingerprint(record: dict[str, JsonValue]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


PI_EVENT_SOURCE_ADAPTER = PiEventSourceAdapter()
PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PI_EVENT_SOURCE_ADAPTER,
    version=PI_EVENT_SOURCE_VERSION,
    projections=(PiEventTextEvidenceProjection(),),
)

__all__ = [
    "PI_EVENT_SOURCE_ADAPTER",
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_EVENT_SOURCE_VERSION",
    "PI_SESSION_CONNECTOR_NAME",
    "PI_SESSION_CONNECTOR_VERSION",
    "PiEventInput",
    "PiEventSource",
    "PiEventSourceAdapter",
    "PiEventTextEvidenceProjection",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
]
