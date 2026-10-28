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

"""HTTP cross-encoder scoring for Memory reranking.

The service scores ``(query, candidate text)`` pairs. Candidates are sent in
bounded batches with their original one-based global ranks, and every batch
response must cover exactly the ranks sent in that request. After all batches
finish, one global ordering over the complete candidate pool decides the final
selection, so a high-scoring candidate from a later batch can outrank an
earlier batch.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage

DEFAULT_HTTP_RERANKER_POLICY = "http-cross-encoder-v1"


class HTTPMemoryReranker:
    """Call an HTTP scoring service and preserve original Memory identities."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = DEFAULT_HTTP_RERANKER_POLICY,
    ) -> None:
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")  # noqa: TRY003
        self.policy_id = policy_id
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score all candidates in bounded batches and select one global order."""

        candidate_count = len(candidates)
        if candidate_count < 1:
            raise ValueError("rerank requires at least one candidate")  # noqa: TRY003
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > candidate_count:
            raise ValueError("rerank limit must be between one and the candidate count")  # noqa: TRY003

        scores: dict[int, float] = {}
        request_count = 0
        for start in range(0, candidate_count, self._batch_size):
            batch = candidates[start : start + self._batch_size]
            expected_ranks = tuple(range(start + 1, start + len(batch) + 1))
            payload = {
                "query": query,
                "candidates": [
                    {"rank": rank, "text": candidate.text}
                    for rank, candidate in zip(expected_ranks, batch, strict=True)
                ],
            }
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            request_count += 1
            scores.update(_parse_scores(response, expected_ranks))

        selected = tuple(sorted(scores, key=lambda rank: (-scores[rank], rank))[:limit])
        return MemoryRerankDecision(
            selected_ranks=selected,
            usage=InferenceUsage(requests=request_count),
        )


def _parse_scores(response: httpx.Response, expected_ranks: tuple[int, ...]) -> dict[int, float]:
    try:
        body: Any = response.json()
    except ValueError as error:
        raise ValueError("reranker response must be valid JSON") from error  # noqa: TRY003
    if not isinstance(body, dict) or set(body) != {"scores"}:
        raise ValueError("reranker response must contain exactly the scores field")  # noqa: TRY003
    items = body["scores"]
    if not isinstance(items, list) or len(items) != len(expected_ranks):
        raise ValueError("reranker response must score exactly the requested batch")  # noqa: TRY003

    expected = set(expected_ranks)
    parsed: dict[int, float] = {}
    for item in items:
        rank, numeric = _parse_score_item(item, expected, parsed)
        parsed[rank] = numeric

    if set(parsed) != expected:
        raise ValueError("reranker response must cover every requested rank")  # noqa: TRY003
    return parsed


def _parse_score_item(
    item: Any,
    expected: set[int],
    parsed: dict[int, float],
) -> tuple[int, float]:
    if not isinstance(item, dict) or set(item) != {"rank", "score"}:
        raise ValueError("reranker score entries must contain exactly rank and score")  # noqa: TRY003
    rank = item["rank"]
    score = item["score"]
    if not isinstance(rank, int) or isinstance(rank, bool) or rank not in expected:
        raise ValueError("reranker response contains a cross-batch or invalid rank")  # noqa: TRY003
    if rank in parsed:
        raise ValueError("reranker response contains a duplicate rank")  # noqa: TRY003
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("reranker score must be a finite number")  # noqa: TRY003, TRY004
    numeric = float(score)
    if not math.isfinite(numeric):
        raise ValueError("reranker score must be a finite number")  # noqa: TRY003
    return rank, numeric


__all__ = ["DEFAULT_HTTP_RERANKER_POLICY", "HTTPMemoryReranker"]
