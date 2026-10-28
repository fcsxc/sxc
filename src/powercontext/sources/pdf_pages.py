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

"""Full-text PDF parsing and page-level Sources for financial reports."""

from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass

from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"
_PAGE_NAME_PREFIX = f"{PDF_PAGE_SOURCE_NAME}:"
_MAX_SOURCE_NAME_LENGTH = 256

_TERM_RE = re.compile(r"[a-z]+\d*|\d+[a-z]*")

_QUERY_FUNCTION_WORDS = frozenset([
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "at", "by", "from", "with",
    "as", "is", "are", "was", "were", "be", "been", "being", "what", "which", "who", "how",
    "why", "when", "where", "do", "does", "did", "can", "could", "should", "would", "i", "we",
    "you", "it", "its", "our", "your", "this", "that", "these", "those", "please",
])


class PDFDocumentInput(BaseModel):
    """One complete original PDF together with a caller-stable document identity."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical PDF page with its extractable text and document summary."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """Captured page content with its durable document identity."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


def _page_source_name(value: PDFPageInput) -> str:
    readable = f"{_PAGE_NAME_PREFIX}{value.document_id}:{value.document_sha256}:{value.page_number}"
    if len(readable) <= _MAX_SOURCE_NAME_LENGTH:
        return readable
    document_digest = hashlib.sha256(f"{value.document_id}\n{value.document_sha256}".encode("utf-8")).hexdigest()
    return f"{_PAGE_NAME_PREFIX}{document_digest}:{value.page_number}"


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of one PDF, failing atomically on invalid input."""

    document_id = value.document_id
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must be a non-empty non-whitespace string")
    content = value.content
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("content must contain the complete original PDF bytes")
    document_sha256 = hashlib.sha256(content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(bytes(content)), strict=True)
        pages = tuple((page.extract_text() or "") for page in reader.pages)
    except (PyPdfError, ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
        raise ValueError("PDF cannot be completely parsed") from error
    return tuple(
        PDFPageInput(
            document_id=document_id,
            document_sha256=document_sha256,
            page_number=page_number,
            text=text,
        )
        for page_number, text in enumerate(pages, start=1)
    )


class PDFPageSourceAdapter:
    """Resolve and read the pdf-page Source."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        return PDFPageSource(
            name=_page_source_name(value),
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one page through the standard text-evidence projection."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDFPageSourceAdapter(),
    version=PDF_PAGE_SOURCE_VERSION,
    projections=(PDFPageTextEvidenceProjection(),),
)


def _terms(text: str) -> list[str]:
    return _TERM_RE.findall(text.lower())


def _parse_page_name(source_id: str) -> tuple[str, int] | None:
    if not source_id.startswith(_PAGE_NAME_PREFIX):
        return None
    rest = source_id[len(_PAGE_NAME_PREFIX):]
    parts = rest.rsplit(":", 2)
    if len(parts) == 3 and re.fullmatch(r"[0-9a-f]{64}", parts[1]) and parts[2].isdigit():
        return parts[0], int(parts[2])
    document_part, separator, page_part = rest.rpartition(":")
    if separator and re.fullmatch(r"[0-9a-f]{64}", document_part) and page_part.isdigit():
        return document_part, int(page_part)
    return None


def _stem(term: str) -> str:
    """Light plural normalization shared by query and page terms."""
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 5 and term.endswith("sses"):
        return term[:-2]
    if len(term) > 4 and term.endswith("xes"):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss") and not term.endswith("us"):
        return term[:-1]
    return term


def _stemmed_terms(text: str) -> list[str]:
    return [_stem(term) for term in _terms(text)]


_QUERY_TAIL_WORDS = frozenset([
    "based", "information", "provided", "primarily", "round", "answer", "two", "decimal", "place",
    "defined", "between", "average", "total", "useful", "metric", "then", "state", "explain",
    "have", "has", "had", "question", "rely", "relying", "assume", "assuming", "perspective",
    "investment", "analyst", "respond", "response", "given", "shown", "within", "details",
    "calculate", "calculating", "give", "mention", "approximately", "roughly", "respectively",
    "exclude", "impact", "overall", "following", "relevant", "meaningful", "conventional",
    "management", "company", "business", "data", "fiscal", "fy", "year", "years", "million",
    "millions", "usd", "percent", "percentage", "note", "notes", "include", "including",
    "included", "amount", "amounts", "determine", "determined", "definition", "requires",
    "required", "requirement", "statement", "financial", "position", "like", "profile", "able",
    "report", "reported", "reports", "materially", "important", "ongoing", "if", "not",
])

_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "geography": (
        "geographic", "geography", "regions", "region", "segments", "segment", "international",
        "countries", "europe", "asia", "africa", "middle east", "latin america",
        "north america", "united states",
    ),
    "margin": ("income", "profit", "revenue", "expense", "cost"),
    "ratio": ("income", "assets", "liabilities", "equity", "sales", "cost"),
    "turnover": ("sales", "cost", "revenue", "inventory"),
    "liquidity": ("cash", "current", "assets", "liabilities"),
    "capital": ("property", "plant", "equipment", "assets"),
    "intensive": ("property", "plant", "equipment", "depreciation", "revenues", "sales", "expenditures"),
    "quick": ("cash", "receivables", "inventories", "current"),
    "segment": ("divisions", "geographic", "reportable"),
    "battle": ("litigation", "lawsuits", "proceedings", "claims", "actions", "disputes"),
    "legal": ("litigation", "proceedings", "lawsuits", "claims"),
    "customer": ("concentration", "largest", "accounted", "government", "airlines"),
    "concentration": ("accounted", "significant", "largest"),
    "cyclicality": ("cyclical", "cycles", "cycle"),
    "growth": ("increase", "increased", "grew", "sales", "volume", "change"),
    "retain": ("retention", "retained", "acquisitions", "record", "attrition"),
    "retention": ("retain", "retained"),
    "drove": ("driven", "primarily", "due"),
    "driven": ("drove", "primarily"),
    "tax": ("provision", "taxes", "pretax"),
    "debt": ("borrowings", "notes", "indebtedness", "maturities", "obligations"),
    "restructuring": ("impairment", "productivity", "charges"),
    "capex": ("capital", "expenditures"),
    "ebitda": ("operating", "depreciation", "amortization"),
    "acquisition": ("acquired", "divestitures", "goodwill", "purchase"),
    "revenue": ("sales", "net"),
    "expense": ("costs", "cost"),
    "employee": ("headcount"),
    "impairment": ("restructuring", "charges"),
    "operate": ("operations", "operating"),
    "income": ("earnings", "profit", "revenues", "expenses"),
    "profit": ("income", "earnings", "margin"),
    "depreciation": ("amortization", "property", "plant", "equipment"),
    "amortization": ("depreciation", "intangible"),
    "inventory": ("inventories", "cost", "sales"),
    "research": ("development"),
    "development": ("research"),
    "primary": ("significant", "substantial", "major", "largest", "principal", "key"),
    "primarily": ("mainly", "largely", "substantially", "principally"),
    "category": ("segments", "segment", "divisions", "types", "commercial", "airplanes", "defense",
                 "unallocated", "eliminations"),
    "improving": ("improved", "increase", "increased", "growth"),
    "changed": ("change", "increase", "decrease"),
    "increased": ("increase", "growth", "grew"),
    "industry": ("industries", "packaging", "sector"),
    "jnj": ("johnson",),
    "amex": ("american", "express"),
    "roa": ("total assets", "net income", "liabilities", "equity"),
}

_PHRASE_EXPANSIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("capital", "intensive"): (
        "property", "plant", "equipment", "depreciation", "amortization",
        "expenditures", "revenues", "operating revenues", "net sales",
        "cost of sales", "operating income", "spectrum", "wireless",
        "network", "fiber", "selling", "general", "administrative", "diluted",
    ),
    ("quick", "ratio"): (
        "cash", "cash equivalents", "receivables", "inventories",
        "current assets", "current liabilities",
    ),
    ("inventory", "turnover"): ("inventories", "cost of sales", "cost of goods sold", "cost of products sold"),
    ("return", "assets"): ("total assets", "net income", "total liabilities"),
    ("gross", "margin"): ("gross profit", "cost of sales", "cost of products sold", "net income", "interest expense"),
    ("operating", "margin"): ("operating income", "operating expenses", "operating profit", "net income", "total revenues"),
    ("effective", "tax"): ("income tax provision", "tax provision", "pretax income"),
    ("tax", "rate"): ("income tax provision", "tax provision", "pretax income"),
    ("cash", "flow"): ("operating activities", "investing activities", "financing activities"),
    ("balance", "sheet"): ("total assets", "total liabilities", "stockholders equity", "shareholders equity"),
    ("legal", "battle"): ("legal proceedings", "legal actions", "litigation", "lawsuits"),
    ("customer", "concentration"): ("accounted for", "net revenue", "net sales"),
    ("high", "growth"): ("sales increased", "increase in sales"),
    ("primary", "customer"): (
        "largest customer", "significant portion", "substantial portion", "limited number",
        "government contracts", "pursuant",
    ),
}

_SPECIAL_TERMS = (
    (re.compile(r"\bm&a\b", re.IGNORECASE), ("acquisitions", "divestitures", "mergers", "acquired")),
    (re.compile(r"\br&d\b", re.IGNORECASE), ("research", "development")),
)

_STATEMENT_MARKERS = (
    ("balance", re.compile(r"consolidated\s+balance\s+sheets?")),
    ("balance", re.compile(r"consolidated\s+statements\s+of\s+financial\s+position")),
    ("income", re.compile(r"consolidated\s+statements?\s+of\s+(?:income|operations|earnings|comprehensive\s+income)")),
    ("cash", re.compile(r"consolidated\s+statements?\s+of\s+cash\s+flows?")),
)

_METRIC_STATEMENT_KINDS: dict[str, frozenset[str]] = {
    "ratio": frozenset(("balance", "income")),
    "quick": frozenset(("balance",)),
    "liquidity": frozenset(("balance",)),
    "turnover": frozenset(("balance", "income")),
    "roa": frozenset(("balance", "income")),
    "margin": frozenset(("income",)),
    "intensive": frozenset(("income", "balance", "cash")),
    "capital": frozenset(("income", "balance", "cash")),
    "ebitda": frozenset(("income", "cash")),
    "flow": frozenset(("cash",)),
    "tax": frozenset(("income",)),
    "debt": frozenset(("balance",)),
    "sheet": frozenset(("balance",)),
    "restructuring": frozenset(("income",)),
    "inventory": frozenset(("balance", "income")),
    "depreciation": frozenset(("cash",)),
    "amortization": frozenset(("cash",)),
}

_STATEMENT_BONUS = 6.0


def _statement_kinds(text: str) -> frozenset[str]:
    normalized = " ".join(text.split()).lower()
    return frozenset(kind for kind, marker in _STATEMENT_MARKERS if marker.search(normalized))


def _query_statement_kinds(query_terms: set[str]) -> frozenset[str]:
    kinds: set[str] = set()
    for term, matched in _METRIC_STATEMENT_KINDS.items():
        if term in query_terms:
            kinds.update(matched)
    if "statement" in query_terms and (
        "income" in query_terms or "operations" in query_terms or "earnings" in query_terms
    ):
        kinds.add("income")
    if "balance" in query_terms and "sheet" in query_terms:
        kinds.add("balance")
    if "financial" in query_terms and "position" in query_terms:
        kinds.add("balance")
    if "cash" in query_terms and "flow" in query_terms:
        kinds.add("cash")
    return frozenset(kinds)


@dataclass(frozen=True)
class _Candidate:
    citation: object
    page_key: tuple
    page_text: str
    terms: tuple[str, ...]
    heading_kinds: frozenset[str]


def _page_text_from_entry(entry_text: str, document_key: str) -> str:
    if entry_text.startswith(f"{document_key}\n"):
        return entry_text[len(document_key) + 1:]
    if entry_text == document_key:
        return ""
    return entry_text


def _collection_candidates(records) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for record in records:
        entry = record.entry
        page_key = None
        for reference in entry.sources:
            parsed = _parse_page_name(reference.source_id)
            if parsed is not None:
                page_key = parsed
                break
        if page_key is None:
            continue
        page_text = _page_text_from_entry(entry.text, page_key[0])
        if not page_text.strip():
            continue
        candidates.append(
            _Candidate(
                citation=record.citation,
                page_key=page_key,
                page_text=page_text,
                terms=tuple(_stemmed_terms(page_text)),
                heading_kinds=_statement_kinds(page_text),
            )
        )
    return candidates


def _analyze_query(question: str) -> tuple[list[str], list[tuple[str, ...]], frozenset[str]]:
    """Return expanded query terms, bonus phrases and statement heading kinds."""
    raw_terms = _TERM_RE.findall(question.lower())
    pre_tail: list[str] = []
    for term in raw_terms:
        if term in _QUERY_FUNCTION_WORDS or _stem(term) in _QUERY_FUNCTION_WORDS:
            continue
        stemmed = _stem(term)
        if len(stemmed) == 1 and not stemmed.isdigit():
            continue
        pre_tail.append(stemmed)
    pre_tail = list(dict.fromkeys(pre_tail))
    content_terms = [term for term in pre_tail if term not in _QUERY_TAIL_WORDS]
    if not content_terms:
        content_terms = pre_tail

    extra: list[str] = []
    fired_phrase_items: list[str] = []
    for pattern, words in _SPECIAL_TERMS:
        if pattern.search(question):
            extra.extend(words)
    for first, second in zip(content_terms, content_terms[1:]):
        expansion = _PHRASE_EXPANSIONS.get((first, second))
        if expansion:
            extra.extend(expansion)
            fired_phrase_items.extend(item for item in expansion if " " in item)
    for term in content_terms:
        expansion = _EXPANSIONS.get(term)
        if expansion:
            extra.extend(expansion)
            fired_phrase_items.extend(item for item in expansion if " " in item)

    expanded: list[str] = list(content_terms)
    for word in extra:
        for part in word.split():
            stemmed = _stem(part)
            if stemmed not in _QUERY_FUNCTION_WORDS and stemmed not in expanded:
                expanded.append(stemmed)

    phrases: list[tuple[str, ...]] = []
    phrase_keys: set[tuple[str, ...]] = set()
    for size in (3, 2):
        for index in range(len(content_terms) - size + 1):
            phrase = tuple(content_terms[index:index + size])
            if all(len(part) > 1 for part in phrase) and phrase not in phrase_keys:
                phrase_keys.add(phrase)
                phrases.append(phrase)
    for item in fired_phrase_items:
        phrase = tuple(_stem(part) for part in item.split())
        if phrase not in phrase_keys:
            phrase_keys.add(phrase)
            phrases.append(phrase)
    return expanded, phrases, _query_statement_kinds(set(pre_tail) | set(expanded))


def _top_distinct(ranked: list[_Candidate], limit: int) -> tuple[object, ...]:
    seen: set[tuple] = set()
    results: list[object] = []
    for candidate in ranked:
        if candidate.page_key in seen:
            continue
        seen.add(candidate.page_key)
        results.append(candidate.citation)
        if len(results) >= limit:
            break
    return tuple(results)


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[object, ...]:
    """Search one scoped Memory and return at most ``limit`` distinct page citations."""

    if limit < 1:
        return ()
    try:
        listing = await memory.list()
        candidates = _collection_candidates(listing.entries)
    except Exception:  # noqa: BLE001 - fall back to the search channel
        candidates = None
    if candidates is not None:
        if candidates:
            return _top_distinct(_rank_pages(question, candidates), limit)
    return await _search_pool_fallback(memory, question, limit)


async def _search_pool_fallback(memory, question: str, limit: int) -> tuple[object, ...]:
    """Search-channel pooling used only when enumerating the Scope is unavailable."""

    from powercontext.artifacts.models import MemoryCitation
    from powercontext.builtin.runtime.models import GetMemoryEntryRequest, SearchMemoryRequest

    query_terms = _terms(question)
    content_terms = list(dict.fromkeys(term for term in query_terms if term not in _QUERY_FUNCTION_WORDS))
    queries: list[str] = []
    if content_terms:
        queries.append(" ".join(content_terms))
    if question.strip():
        queries.append(question.strip())
    numbers = list(dict.fromkeys(term for term in query_terms if term.isdigit() and len(term) >= 2))
    if len(numbers) >= 2:
        queries.append(" ".join(numbers))

    pool_size = min(max(limit * 6, 60), 300)
    pooled: dict[tuple, tuple] = {}
    first_error: Exception | None = None
    mode = "fts"
    for query in queries:
        try:
            page = await memory.search(SearchMemoryRequest(query=query, limit=pool_size, mode=mode))
        except Exception as error:  # noqa: BLE001 - a failed variant must not sink the search
            if mode == "fts":
                mode = "auto"
                try:
                    page = await memory.search(SearchMemoryRequest(query=query, limit=pool_size, mode=mode))
                except Exception:  # noqa: BLE001
                    if first_error is None:
                        first_error = error
                    continue
            else:
                if first_error is None:
                    first_error = error
                continue
        for hit in page.hits:
            key = (hit.memory_ref.artifact_id, hit.memory_ref.revision, hit.entry_id, hit.entry_version_id)
            if key in pooled:
                continue
            pooled[key] = (
                MemoryCitation(
                    memory_ref=hit.memory_ref,
                    entry_id=hit.entry_id,
                    entry_version_id=hit.entry_version_id,
                ),
                hit,
            )
    if not pooled and first_error is not None:
        raise first_error

    candidates: list[_Candidate] = []
    for citation, hit in pooled.values():
        try:
            record = await memory.get(GetMemoryEntryRequest(citation=citation))
        except Exception:  # noqa: BLE001 - a stale entry must not sink the search
            continue
        entry = record.entry
        page_key = None
        for reference in entry.sources:
            parsed = _parse_page_name(reference.source_id)
            if parsed is not None:
                page_key = parsed
                break
        if page_key is None:
            continue
        page_text = _page_text_from_entry(entry.text, page_key[0])
        if not page_text.strip():
            continue
        candidates.append(
            _Candidate(
                citation=citation,
                page_key=page_key,
                page_text=page_text,
                terms=tuple(_stemmed_terms(page_text)),
                heading_kinds=_statement_kinds(page_text),
            )
        )
    return _top_distinct(_rank_pages(question, candidates), limit)


def _rank_pages(question: str, candidates: list[_Candidate]) -> list[_Candidate]:
    if not candidates:
        return []
    query_terms, phrases, statement_kinds = _analyze_query(question)

    document_frequency: dict[str, int] = {}
    for candidate in candidates:
        for term in set(candidate.terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    total = len(candidates)
    average_length = sum(len(candidate.terms) for candidate in candidates) / total
    inverse_frequency = {
        term: math.log((total + 1) / (document_frequency.get(term, 0) + 1)) + 1 for term in query_terms
    }

    scored: list[tuple[float, int, _Candidate]] = []
    k1, b = 1.2, 0.75
    for index, candidate in enumerate(candidates):
        terms = candidate.terms
        frequencies: dict[str, int] = {}
        for term in terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        length = len(terms)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + k1 * (1 - b + b * length / average_length)
            score += inverse_frequency.get(term, 1.0) * frequency * (k1 + 1) / denominator
        if phrases:
            joined = " ".join(terms)
            for phrase in phrases:
                occurrences = joined.count(" ".join(phrase))
                if occurrences:
                    phrase_weight = sum(inverse_frequency.get(term, 1.0) for term in phrase)
                    score += min(occurrences, 3) * phrase_weight * 0.5
        document_key = candidate.page_key[0].lower()
        matched = sum(1 for term in query_terms if len(term) > 1 and term in document_key)
        if matched:
            score += min(matched, 2) * 6.0
        if statement_kinds and statement_kinds & candidate.heading_kinds:
            score += _STATEMENT_BONUS
        scored.append((score, -index, candidate))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored]


__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDFDocumentInput",
    "PDFPageInput",
    "parse_pdf_document",
    "search_pdf_pages",
]
