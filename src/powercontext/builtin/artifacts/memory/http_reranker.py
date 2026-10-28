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

"""HTTP scoring adapter for listwise Memory reranking."""

from __future__ import annotations

import math

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision, _validate_bounds
from powercontext.builtin.inference import InferenceUsage


class HTTPMemoryReranker:
    """Score Memory candidates with an offline HTTP service across bounded batches.

    Requests carry each candidate's one-based rank from the full coarse pool,
    so service scores map back to the original hits without renumbering.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least one")  # noqa: TRY003
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size
        self.policy_id = policy_id

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Request service scores in bounded batches and merge one global sort."""

        _validate_bounds(len(candidates), limit)
        scores: dict[int, float] = {}
        requests = 0
        for offset in range(0, len(candidates), self._batch_size):
            batch = candidates[offset : offset + self._batch_size]
            payload = {
                "query": query,
                "candidates": [
                    {"rank": offset + position, "text": candidate.text}
                    for position, candidate in enumerate(batch, start=1)
                ],
            }
            response = await self._client.post(self._endpoint, json=payload)
            requests += 1
            response.raise_for_status()
            scores.update(_parse_batch_scores(response, offset + 1, len(batch)))
        ordered = sorted(scores, key=lambda rank: (-scores[rank], rank))
        return MemoryRerankDecision(
            selected_ranks=tuple(ordered[:limit]),
            usage=InferenceUsage(requests=requests),
        )


def _parse_batch_scores(
    response: httpx.Response,
    first_rank: int,
    count: int,
) -> dict[int, float]:
    """Validate one batch response and return its rank-to-score mapping."""

    try:
        body = response.json()
    except ValueError as error:
        raise ValueError("reranker response is not valid JSON") from error  # noqa: TRY003
    if not isinstance(body, dict) or set(body) != {"scores"}:
        raise ValueError("reranker response must contain exactly a scores field")  # noqa: TRY003
    records = body["scores"]
    if not isinstance(records, list):
        raise ValueError("reranker response scores must be a list")  # noqa: TRY003
    parsed: dict[int, float] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"rank", "score"}:
            raise ValueError("each score record must contain exactly rank and score")  # noqa: TRY003
        rank = record["rank"]
        score = record["score"]
        if isinstance(rank, bool) or not isinstance(rank, int):
            raise ValueError("score rank must be an integer")  # noqa: TRY003
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("score must be a number")  # noqa: TRY003
        if not math.isfinite(score):
            raise ValueError("score must be finite")  # noqa: TRY003
        if rank in parsed:
            raise ValueError("score ranks must be unique within a response")  # noqa: TRY003
        parsed[rank] = float(score)
    if set(parsed) != set(range(first_rank, first_rank + count)):
        raise ValueError("scores must cover each requested rank exactly once")  # noqa: TRY003
    return parsed


__all__ = ["HTTPMemoryReranker"]
