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

"""Row-level Sources captured from one offline CSV document.

Each data record becomes an independent ``CAPTURED`` Source identified by the
document identity and the exact primary-key value. Field order and raw string
values are preserved so an evidence reference can be resolved back to the
complete original record.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from typing import cast
from urllib.parse import quote

from pydantic import BaseModel, model_validator

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
CSV_ROW_SOURCE_VERSION = "1"


class CSVDocumentInput(BaseModel):
    """One complete offline CSV document plus its row-identity selection."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One parsed CSV record in original header order."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]

    @model_validator(mode="after")
    def validate_row_shape(self) -> CSVRowInput:
        if not self.columns:
            raise ValueError("CSV row must contain at least one column")  # noqa: TRY003
        if len(self.columns) != len(self.values):
            raise ValueError("CSV row columns and values must have the same width")  # noqa: TRY003
        return self


class CSVRowSource(Source):
    """Durable evidence for exactly one captured CSV record."""

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]

    @model_validator(mode="after")
    def validate_source_identity(self) -> CSVRowSource:
        if self.source_id != self.name:
            raise ValueError("source_id must equal the Source name identity")  # noqa: TRY003
        if len(self.columns) != len(self.values):
            raise ValueError("CSV row columns and values must have the same width")  # noqa: TRY003
        return self


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Parse and validate one complete CSV document, atomically.

    The whole document is validated before any row is returned. Encoding, CSV
    syntax, header, width, primary-key, and identity errors raise ``ValueError``
    and never expose a partial result.
    """

    document_id = value.document_id
    _validate_document_id(document_id)
    primary_key = value.primary_key
    _validate_primary_key(primary_key)
    reader = _open_reader(value.content)
    header = _read_header(reader)
    primary_key_index = _locate_primary_key(header, primary_key)
    return _read_records(
        reader,
        document_id=document_id,
        primary_key=primary_key,
        columns=header,
        primary_key_index=primary_key_index,
    )


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Build the delimiter-safe, bounded identity of one CSV row Source."""

    _validate_document_id(document_id)
    if not isinstance(primary_key_value, str) or not primary_key_value.strip():
        raise ValueError("primary_key_value must be a non-empty string")  # noqa: TRY003
    source_id = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(  # noqa: TRY003
            f"csv row source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters"
        )
    return source_id


def _open_reader(content: bytes) -> Iterator[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV content must be strict UTF-8") from error  # noqa: TRY003
    return cast(Iterator[list[str]], csv.reader(io.StringIO(text, newline=""), strict=True))


def _read_header(reader: Iterator[list[str]]) -> tuple[str, ...]:
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("CSV document must contain a header record") from None  # noqa: TRY003
    except csv.Error as error:
        raise ValueError(f"malformed CSV content: {error}") from error  # noqa: TRY003
    if not header:
        raise ValueError("CSV header must contain at least one column")  # noqa: TRY003
    seen_columns: set[str] = set()
    for column in header:
        if not column or not column.strip():
            raise ValueError("CSV header columns must be non-empty and non-blank")  # noqa: TRY003
        if column in seen_columns:
            raise ValueError(f"CSV header column {column!r} is duplicated")  # noqa: TRY003
        seen_columns.add(column)
    return tuple(header)


def _locate_primary_key(header: tuple[str, ...], primary_key: str) -> int:
    try:
        return header.index(primary_key)
    except ValueError:
        raise ValueError(  # noqa: TRY003
            f"primary_key {primary_key!r} does not match a CSV header column"
        ) from None


def _read_records(
    reader: Iterator[list[str]],
    *,
    document_id: str,
    primary_key: str,
    columns: tuple[str, ...],
    primary_key_index: int,
) -> tuple[CSVRowInput, ...]:
    rows: list[CSVRowInput] = []
    seen_keys: set[str] = set()
    try:
        for record in reader:
            if not record:
                # Completely empty physical records carry no cells and are ignored.
                continue
            if len(record) != len(columns):
                raise ValueError(  # noqa: TRY003
                    f"CSV record width {len(record)} does not match header width {len(columns)}"
                )
            primary_key_value = record[primary_key_index]
            if not primary_key_value.strip():
                raise ValueError("CSV primary-key value must not be empty or blank")  # noqa: TRY003
            if primary_key_value in seen_keys:
                raise ValueError(f"CSV primary-key value {primary_key_value!r} is duplicated")  # noqa: TRY003
            seen_keys.add(primary_key_value)
            # Validate the stable identity while the document is still being parsed,
            # so an over-long identity can never yield a partial result.
            csv_row_source_id(document_id, primary_key_value)
            rows.append(
                CSVRowInput(
                    document_id=document_id,
                    primary_key=primary_key,
                    primary_key_value=primary_key_value,
                    columns=columns,
                    values=tuple(record),
                )
            )
    except csv.Error as error:
        raise ValueError(f"malformed CSV content: {error}") from error  # noqa: TRY003
    return tuple(rows)


def _validate_document_id(document_id: object) -> None:
    if not isinstance(document_id, str) or not document_id.strip() or document_id != document_id.strip():
        raise ValueError(  # noqa: TRY003
            "document_id must be a non-empty string without leading or trailing whitespace"
        )


def _validate_primary_key(primary_key: object) -> None:
    if not isinstance(primary_key, str) or not primary_key.strip():
        raise ValueError("primary_key must be a non-empty string")  # noqa: TRY003


class CSVRowSourceAdapter:
    """Resolve one parsed row into its captured Source and read it back exactly."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


class CSVRowTextEvidenceProjection:
    """Expose one complete original record as standard textual evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_ADAPTER = CSVRowSourceAdapter()
CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    version=CSV_ROW_SOURCE_VERSION,
    projections=(CSVRowTextEvidenceProjection(),),
)

__all__ = [
    "CSV_ROW_SOURCE_ADAPTER",
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CSV_ROW_SOURCE_VERSION",
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "CSVRowSourceAdapter",
    "CSVRowTextEvidenceProjection",
    "csv_row_source_id",
    "parse_csv_document",
]
