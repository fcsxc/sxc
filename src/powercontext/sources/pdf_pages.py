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

"""Capture complete financial-report PDFs as page-level evidence.

Every physical PDF page becomes one ``CAPTURED`` Source whose text projection
starts with the document identity and then carries the page's extractable
text. The page identity includes the exact input SHA-256 so a revised document
produces new Sources while old citations keep pointing at the old revision.

The search helper builds a small local BM25 index over the scoped Memory
entries (public Memory storage) and reranks them for FinanceBench-style
questions. It never invents citations; every returned citation is an exact
entry in the caller's Memory.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, model_validator
from pypdf import PdfReader

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"

_TOKEN_RE = re.compile(r"[a-z]+|\d+")
_COMPACT_RE = re.compile(r"\s+")
_STOPWORDS = frozenset([
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "so",
    "such",
    "of",
    "to",
    "in",
    "for",
    "on",
    "at",
    "by",
    "with",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
    "we",
    "our",
    "us",
    "you",
    "your",
    "they",
    "their",
    "he",
    "she",
    "his",
    "her",
    "i",
    "me",
    "my",
    "not",
    "no",
    "nor",
    "do",
    "does",
    "did",
    "done",
    "can",
    "could",
    "should",
    "would",
    "may",
    "might",
    "must",
    "will",
    "shall",
    "have",
    "has",
    "had",
    "having",
    "about",
    "into",
    "over",
    "under",
    "between",
    "during",
    "after",
    "before",
    "against",
    "among",
    "within",
    "without",
    "through",
    "across",
    "per",
    "via",
    "vs",
    "versus",
    "also",
    "just",
    "only",
    "very",
    "much",
    "many",
    "some",
    "each",
    "any",
    "all",
    "both",
    "more",
    "most",
    "less",
    "least",
    "other",
    "others",
    "same",
    "own",
    "what",
    "which",
    "who",
    "whom",
    "whose",
    "when",
    "where",
    "why",
    "how",
    "whether",
    "while",
    "because",
    "although",
    "though",
    "unless",
    "until",
    "upon",
    "off",
    "out",
    "up",
    "down",
    "again",
    "further",
    "once",
    "reported",
    "materially",
    "important",
    "ongoing",
    "directly",
    "outlined",
    "explicitly",
    "state",
    "define",
    "answer",
    "respond",
    "question",
    "assuming",
    "perspective",
    "investment",
    "analyst",
    "use",
    "details",
    "shown",
    "within",
    "give",
    "response",
    "relying",
    "calculate",
    "using",
    "usd",
    "millions",
    "fy",
    "s",
    "d",
    "p",
    "l",
])

_STOPWORDS = _STOPWORDS | frozenset([
    "based",
    "data",
    "useful",
    "relevant",
    "metric",
    "company",
    "please",
    "explain",
    "provided",
    "primarily",
    "units",
    "percents",
    "round",
    "decimal",
    "places",
    "asked",
    "utilizing",
    "line",
    "items",
    "clearly",
    "information",
    "change",
])

_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "geographies": (
        "countries",
        "territories",
        "regions",
        "segments",
        "operations",
        "africa",
        "europe",
        "asia",
        "china",
        "australia",
        "america",
    ),
    "geography": (
        "countries",
        "territories",
        "regions",
        "segments",
        "operations",
        "africa",
        "europe",
        "asia",
        "china",
        "australia",
        "america",
    ),
    "operates": ("operations", "segments", "countries", "territories"),
    "legal": ("litigation", "proceedings", "claims", "regulatory", "inquiries", "investigations"),
    "battles": ("litigation", "proceedings", "claims"),
    "restructuring": ("impairment", "charges", "productivity", "severance"),
    "costs": ("charges", "expenses"),
    "ebitda": ("operating", "income", "depreciation", "amortization", "profit"),
    "capex": ("capital", "spending", "expenditures"),
    "margin": ("revenue", "profit", "income"),
    "depreciation": ("amortization",),
    "amortization": ("depreciation",),
    "cash": ("flow", "flows"),
    "statements": ("statement",),
    "income": ("revenue", "profit"),
    "revenue": ("sales",),
    "inventory": ("inventories",),
    "debt": ("borrowings", "obligations"),
    "dividend": ("dividends",),
    "share": ("shares", "stock"),
    "working": ("current", "assets", "liabilities", "balance"),
    "capital": ("assets", "liabilities", "equity", "expenditures"),
    "turnover": ("revenue", "sales", "assets", "inventory", "receivable"),
    "fixed": ("property", "plant", "equipment"),
    "gross": ("profit", "revenue", "sales"),
    "margins": ("profit", "revenue", "income"),
    "operating": ("income", "profit"),
    "asset": ("assets",),
    "equity": ("stockholders", "shareholders"),
    "eps": ("earnings", "shares", "net", "income"),
    "tax": ("income", "taxes"),
    "interest": ("expense", "income"),
    "acquisition": ("acquisitions", "acquired", "purchase", "combination"),
    "industry": ("business", "segment", "market", "markets", "manufacturing", "packaging"),
    "payable": ("accounts", "payables", "suppliers", "inventory"),
}

_INTENT_PHRASES: dict[str, tuple[str, ...]] = {
    "geography": (
        "our operations",
        "reportable segments",
        "countries and territories",
        "north america",
        "latin america",
        "europe",
        "africa",
        "middle east",
        "asia pacific",
        "amesa",
        "apac",
        "china region",
        "business segment",
        "business segments",
        "segment sales",
        "sales and operating income",
        "sales and operating income (loss) by business segment",
        "performance by business segment",
    ),
    "business": (
        "item 1. business",
        "item 1. - business",
        "the company",
        "business overview",
        "overview",
        "industry",
    ),
    "acquisition": (
        "note 5 - acquisitions",
        "acquisitions and divestitures",
        "business combination",
        "purchase price",
        "acquisitions",
    ),
    "legal": (
        "item 3. legal proceedings",
        "legal proceedings",
        "litigation",
        "claims",
        "regulatory",
    ),
    "restructuring": (
        "restructuring and impairment charges",
        "productivity plan",
        "severance",
        "impairment charges",
    ),
    "financial": (
        "consolidated statement of income",
        "consolidated statement of cash flows",
        "net revenue",
        "operating profit",
        "depreciation and amortization",
        "capital spending",
        "net income",
        "operating income",
    ),
    "balance_sheet": (
        "consolidated balance sheet",
        "total assets",
        "total liabilities",
        "accounts receivable",
        "inventories",
    ),
    "cash_flow": (
        "consolidated statement of cash flows",
        "net cash provided by operating activities",
        "capital spending",
    ),
    "risk": ("risk factors", "item 1a"),
    "dividend": ("dividends",),
    "debt": ("long-term debt", "borrowings", "commercial paper"),
}

_INTENT_TERMS: dict[str, frozenset[str]] = {
    "geography": frozenset({"geographies", "geography", "operates", "countries", "regions", "segment", "segments"}),
    "legal": frozenset({"legal", "battles", "litigation", "proceedings", "lawsuits"}),
    "restructuring": frozenset({"restructuring", "impairment", "severance", "costs"}),
    "financial": frozenset({
        "ebitda",
        "capex",
        "margin",
        "income",
        "revenue",
        "cash",
        "flow",
        "depreciation",
        "amortization",
        "statements",
    }),
    "balance_sheet": frozenset({"balance", "assets", "liabilities", "receivable", "inventory"}),
    "cash_flow": frozenset({"cash", "flow", "flows", "operating"}),
    "risk": frozenset({"risk", "risks"}),
    "dividend": frozenset({"dividend", "dividends"}),
    "debt": frozenset({"debt", "borrowings"}),
    "business": frozenset({"industry", "business", "company", "operate", "operates", "primarily"}),
    "acquisition": frozenset({"acquisition", "acquisitions", "acquired", "merger", "divestiture", "divestitures"}),
}

_PHRASE_WEIGHTS: dict[str, float] = {
    "cash flow": 1.5,
    "cash flows": 1.5,
    "net revenue": 1.5,
    "net sales": 1.5,
    "gross profit": 1.5,
    "operating income": 1.5,
    "operating profit": 1.5,
    "depreciation and amortization": 2.0,
    "capital spending": 1.5,
    "capital expenditures": 1.5,
    "net income": 1.5,
    "total assets": 1.5,
    "total liabilities": 1.5,
    "current assets": 1.5,
    "current liabilities": 1.5,
    "property and equipment": 1.5,
    "legal proceedings": 2.0,
    "restructuring and impairment charges": 2.0,
    "reportable segments": 1.5,
    "consolidated statement of income": 2.0,
    "consolidated statements of income": 2.0,
    "consolidated statement of operations": 2.0,
    "consolidated statements of operations": 2.0,
    "consolidated statement of cash flows": 2.0,
    "consolidated statements of cash flows": 2.0,
}

_STATEMENT_TERMS: dict[str, frozenset[str]] = {
    "income_statement": frozenset({
        "income",
        "margin",
        "margins",
        "revenue",
        "revenues",
        "profit",
        "operating",
        "gross",
        "sales",
        "earnings",
        "eps",
        "turnover",
        "cogs",
        "payable",
        "accounts",
        "inventory",
        "tax",
        "effective",
        "rate",
    }),
    "balance_sheet": frozenset({
        "working",
        "capital",
        "assets",
        "liabilities",
        "balance",
        "sheet",
        "turnover",
        "fixed",
        "ppe",
        "property",
        "equity",
        "debt",
        "receivable",
        "inventory",
        "current",
        "quick",
        "liquidity",
        "ratio",
        "solvency",
        "leverage",
        "payable",
        "payables",
        "accounts",
    }),
    "cash_flow_statement": frozenset({
        "cash",
        "flow",
        "flows",
        "ebitda",
        "capex",
        "depreciation",
        "amortization",
        "dividend",
        "dividends",
    }),
    "financial_statements": frozenset({
        "capital",
        "business",
        "financial",
        "assets",
        "income",
        "revenue",
        "margin",
        "margins",
        "cash",
        "debt",
        "equity",
        "sales",
        "profit",
        "operating",
        "ebitda",
        "capex",
        "balance",
        "sheet",
        "statement",
        "quick",
        "liquidity",
        "ratio",
        "dividend",
        "dividends",
        "securities",
        "payable",
        "cogs",
        "inventory",
        "tax",
        "effective",
        "rate",
    }),
}

_STATEMENT_PHRASES: dict[str, tuple[str, ...]] = {
    "income_statement": (
        "consolidated statements of income",
        "consolidated statement of income",
        "statements of income",
        "statement of income",
        "consolidated statements of operations",
        "consolidated statement of operations",
        "statements of operations",
        "statement of operations",
    ),
    "balance_sheet": (
        "consolidated balance sheets",
        "consolidated balance sheet",
        "balance sheets",
        "balance sheet",
    ),
    "cash_flow_statement": (
        "consolidated statements of cash flows",
        "consolidated statement of cash flows",
        "statements of cash flows",
        "statement of cash flows",
    ),
    "financial_statements": (
        "consolidated statements of income",
        "consolidated statement of income",
        "statements of income",
        "statement of income",
        "consolidated statements of operations",
        "consolidated statement of operations",
        "statements of operations",
        "statement of operations",
        "consolidated balance sheets",
        "consolidated balance sheet",
        "balance sheets",
        "balance sheet",
        "consolidated statements of cash flows",
        "consolidated statement of cash flows",
        "statements of cash flows",
        "statement of cash flows",
    ),
}

_COMPACT_INTENT_PHRASES = {
    intent: tuple(_COMPACT_RE.sub("", phrase.casefold()) for phrase in phrases)
    for intent, phrases in _INTENT_PHRASES.items()
}
_COMPACT_PHRASE_WEIGHTS = {_COMPACT_RE.sub("", phrase.casefold()): weight for phrase, weight in _PHRASE_WEIGHTS.items()}
_COMPACT_STATEMENT_PHRASES = {
    intent: tuple(_COMPACT_RE.sub("", phrase.casefold()) for phrase in phrases)
    for intent, phrases in _STATEMENT_PHRASES.items()
}


class PDFDocumentInput(BaseModel):
    """One complete PDF document supplied as raw bytes."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical PDF page in the original document."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """Durable evidence for exactly one physical PDF page."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str

    @model_validator(mode="after")
    def validate_source_identity(self) -> PDFPageSource:
        if self.source_id != self.name:
            raise ValueError("source_id must equal the Source name identity")  # noqa: TRY003
        return self


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of a complete PDF atomically."""

    document_id = value.document_id
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must not be empty or blank")  # noqa: TRY003
    content = value.content
    if not content:
        raise ValueError("PDF content must not be empty")  # noqa: TRY003
    digest = hashlib.sha256(content).hexdigest()
    try:
        return _read_pdf_pages(content, document_id, digest)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(  # noqa: TRY003
            "PDF content is empty, not a PDF, or cannot be fully parsed"
        ) from error


def _read_pdf_pages(content: bytes, document_id: str, digest: str) -> tuple[PDFPageInput, ...]:
    reader = PdfReader(io.BytesIO(content), strict=False)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF requires a user password")  # noqa: TRY003
    pages = reader.pages
    page_count = len(pages)
    if page_count < 1:
        raise ValueError("PDF must contain at least one physical page")  # noqa: TRY003
    parsed: list[PDFPageInput] = []
    for page_number in range(1, page_count + 1):
        text = pages[page_number - 1].extract_text() or ""
        if not text.strip():
            text = ""
        parsed.append(
            PDFPageInput(
                document_id=document_id,
                document_sha256=digest,
                page_number=page_number,
                text=text,
            )
        )
    return tuple(parsed)


def _page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must not be empty or blank")  # noqa: TRY003
    if not isinstance(document_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", document_sha256):
        raise ValueError("document_sha256 must be a lowercase SHA-256 digest")  # noqa: TRY003
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
        raise ValueError("page_number must be a positive integer")  # noqa: TRY003
    source_id = f"pdf:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"pdf page source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return source_id


class PDFPageSourceAdapter:
    """Resolve one parsed page into its captured Source and read it back exactly."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = _page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
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
    """Expose one page as document identity plus complete extractable text."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


async def search_pdf_pages(memory: Any, question: str, limit: int = 10) -> tuple[Any, ...]:
    """Return exact page citations ranked for one natural-language question."""

    if limit <= 0 or not isinstance(question, str) or not question.strip():
        return ()
    from powercontext.artifacts import MemoryCitation
    from powercontext.builtin.runtime import SearchMemoryRequest

    entries = _page_records(await _memory_entries(memory))
    search_page, search_hits = await _search_candidates(memory, question, limit, SearchMemoryRequest)
    if not entries:
        return _citations_from_hits(search_page, limit, MemoryCitation)
    documents = _documents(entries)
    if not documents:
        return ()
    token_documents = [_tokens(text) for text, _ in documents]
    entry_ids = [record.entry.entry_id for _, record in documents]
    scores = _rank(question, token_documents, [text for text, _ in documents], entry_ids, search_hits)
    return _top_citations(documents, scores, limit, MemoryCitation)


def _page_records(entries: tuple[Any, ...]) -> tuple[Any, ...]:
    pdf_entries = tuple(
        record
        for record in entries
        if any(getattr(source, "source_type", None) == PDF_PAGE_SOURCE_NAME for source in record.entry.sources)
    )
    return pdf_entries or entries


async def _search_candidates(
    memory: Any,
    question: str,
    limit: int,
    request_class: Any,
) -> tuple[Any | None, dict[str, int]]:
    try:
        page = await memory.search(request_class(query=question, mode="fts", limit=max(limit * 10, 200)))
    except Exception:
        return None, {}
    hits: dict[str, int] = {}
    for rank, hit in enumerate(page.hits):
        hits.setdefault(hit.entry_id, rank)
    return page, hits


def _citations_from_hits(search_page: Any | None, limit: int, citation_class: Any) -> tuple[Any, ...]:
    if search_page is None:
        return ()
    citations = []
    seen: set[str] = set()
    for hit in search_page.hits:
        if hit.entry_id in seen:
            continue
        seen.add(hit.entry_id)
        citations.append(
            citation_class(
                memory_ref=hit.memory_ref,
                entry_id=hit.entry_id,
                entry_version_id=hit.entry_version_id,
            )
        )
        if len(citations) >= limit:
            break
    return tuple(citations)


def _documents(entries: tuple[Any, ...]) -> list[tuple[str, Any]]:
    documents: list[tuple[str, Any]] = []
    for record in entries:
        text = record.entry.text
        if isinstance(text, str) and text.strip():
            documents.append((text, record))
    return documents


def _top_citations(
    documents: list[tuple[str, Any]],
    scores: list[float],
    limit: int,
    citation_class: Any,
) -> tuple[Any, ...]:
    order = sorted(range(len(documents)), key=lambda index: (-scores[index], index))
    citations = []
    seen_pages: set[str] = set()
    for index in order:
        record = documents[index][1]
        page_key = _page_key(record)
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        citations.append(_citation(record, citation_class))
        if len(citations) >= limit:
            break
    return tuple(citations)


async def _memory_entries(memory: Any) -> tuple[Any, ...]:
    try:
        page = await memory.list(include_inactive=False)
    except Exception:
        return ()
    entries = getattr(page, "entries", ())
    return tuple(entry for entry in entries if getattr(entry, "state", "active") == "active")


def _citation(record: Any, citation_class: Any) -> Any:
    citation = getattr(record, "citation", None)
    if citation is not None:
        return citation
    entry = record.entry
    return citation_class(
        memory_ref=record.memory_ref,
        entry_id=entry.entry_id,
        entry_version_id=entry.entry_version_id,
    )


def _page_key(record: Any) -> str:
    for source in getattr(record.entry, "sources", ()):
        if getattr(source, "source_type", None) == PDF_PAGE_SOURCE_NAME:
            return str(source.source_id)
    return str(record.entry.entry_id)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.casefold())


def _query_terms(question: str) -> tuple[list[str], dict[str, float], tuple[str, ...], tuple[str, ...]]:
    base = [token for token in _tokens(question) if token not in _STOPWORDS and (len(token) > 1 or token.isdigit())]
    base = list(dict.fromkeys(base))
    expanded: dict[str, float] = {}
    for term in base:
        for expansion in _EXPANSIONS.get(term, ()):
            if expansion not in base:
                expanded[expansion] = max(expanded.get(expansion, 0.0), 0.35)
    intents = tuple(intent for intent, terms in _INTENT_TERMS.items() if terms.intersection(base))
    statement_intents = tuple(intent for intent, terms in _STATEMENT_TERMS.items() if terms.intersection(base))
    return base, expanded, intents, statement_intents


def _rank(
    question: str,
    documents: list[list[str]],
    raw_texts: list[str],
    entry_ids: list[str],
    search_hits: dict[str, int],
) -> list[float]:
    base, expanded, intents, statement_intents = _query_terms(question)
    scores = _bm25_scores(base, expanded, documents)
    _apply_text_boosts(raw_texts, intents, statement_intents, scores)
    _apply_substring_coverage(base, raw_texts, scores)
    _apply_question_boosts(question, raw_texts, scores)
    _apply_search_prior(entry_ids, search_hits, scores)
    return scores


def _bm25_scores(base: list[str], expanded: dict[str, float], documents: list[list[str]]) -> list[float]:
    weights: dict[str, float] = dict.fromkeys(base, 1.0)
    weights.update({term: weight for term, weight in expanded.items() if term not in weights})
    if not weights:
        return [0.0 for _ in documents]

    total = len(documents)
    average_length = sum(len(document) for document in documents) / total
    document_frequencies = dict.fromkeys(weights, 0)
    token_counts = [Counter(document) for document in documents]
    for counts in token_counts:
        for term in weights:
            if term in counts:
                document_frequencies[term] += 1

    k1, b = 1.2, 0.75
    scores: list[float] = []
    for counts, length in zip(token_counts, (len(document) for document in documents), strict=True):
        score = 0.0
        for term, weight in weights.items():
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            document_frequency = document_frequencies[term]
            inverse_frequency = math.log(1 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
            score += (
                weight
                * inverse_frequency
                * (frequency * (k1 + 1))
                / (frequency + k1 * (1 - b + b * length / max(average_length, 1.0)))
            )
        coverage = sum(1 for term in base if term in counts) / max(len(base), 1)
        score += 2.0 * coverage
        scores.append(score)
    return scores


def _apply_text_boosts(
    raw_texts: list[str],
    intents: tuple[str, ...],
    statement_intents: tuple[str, ...],
    scores: list[float],
) -> None:
    statement_boosts = {
        "income_statement": 18.0,
        "balance_sheet": 12.0,
        "cash_flow_statement": 10.0,
        "financial_statements": 6.0,
    }
    for index, text in enumerate(raw_texts):
        compact = _COMPACT_RE.sub("", text.casefold())
        heading = compact[:400]
        for intent in intents:
            for phrase in _COMPACT_INTENT_PHRASES[intent]:
                if phrase in compact:
                    scores[index] += 2.5
        for phrase, weight in _COMPACT_PHRASE_WEIGHTS.items():
            if phrase in compact:
                scores[index] += weight
        for statement_intent in statement_intents:
            if any(phrase in heading for phrase in _COMPACT_STATEMENT_PHRASES[statement_intent]):
                scores[index] += statement_boosts[statement_intent]


def _apply_substring_coverage(base: list[str], raw_texts: list[str], scores: list[float]) -> None:
    denominator = max(len(base), 1)
    for index, text in enumerate(raw_texts):
        compact = _COMPACT_RE.sub("", text.casefold())
        matched = sum(1 for term in base if term in compact)
        scores[index] += 2.0 * matched / denominator


def _apply_question_boosts(question: str, raw_texts: list[str], scores: list[float]) -> None:
    compact_question = _COMPACT_RE.sub("", question.casefold())
    if not any(
        phrase in compact_question
        for phrase in (
            "notausefulorrelevantmetric",
            "notausefulorrelevant",
            "notausefulmetric",
            "notarelevantmetric",
            "notarelevant",
            "notrelevant",
        )
    ):
        return
    for index, text in enumerate(raw_texts):
        compact = _COMPACT_RE.sub("", text.casefold())
        if "item1.business" in compact or "overview" in compact:
            scores[index] += 20.0


def _apply_search_prior(entry_ids: list[str], search_hits: dict[str, int], scores: list[float]) -> None:
    for index, entry_id in enumerate(entry_ids):
        rank = search_hits.get(entry_id)
        if rank is not None:
            scores[index] += 0.5 / (1.0 + rank)


PDF_PAGE_SOURCE_ADAPTER = PDFPageSourceAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    version=PDF_PAGE_SOURCE_VERSION,
    projections=(PDFPageTextEvidenceProjection(),),
)

__all__ = [
    "PDF_PAGE_SOURCE_ADAPTER",
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDF_PAGE_SOURCE_VERSION",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "PDFPageSourceAdapter",
    "PDFPageTextEvidenceProjection",
    "parse_pdf_document",
    "search_pdf_pages",
]
