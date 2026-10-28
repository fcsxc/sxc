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

"""Coalesce concurrent embedding calls and cache successful vectors."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(slots=True)
class _Batch:
    texts: list[str] = field(default_factory=list)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[_BatchOutcome] | None = None
    closed: bool = False


@dataclass(frozen=True, slots=True)
class _BatchOutcome:
    vectors: dict[str, tuple[float, ...]]
    usage: InferenceUsage


class CoalescingEmbeddingModel:
    """Share one provider batch between callers and retain successful vectors."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if not isinstance(max_batch_size, int) or isinstance(max_batch_size, bool) or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if not isinstance(cache_size, int) or isinstance(cache_size, bool) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")  # noqa: TRY003
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be a non-negative number")  # noqa: TRY003
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._inflight: dict[str, _Batch] = {}
        self._open_batches: list[_Batch] = []
        self._lock = asyncio.Lock()

    @property
    def profile(self):
        return self._model.profile

    async def embed(self, texts: Sequence[str], /) -> EmbeddingResult:
        """Return vectors in input order, preserving duplicates and usage."""

        requested = tuple(texts)
        if not requested:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))
        unique = tuple(dict.fromkeys(requested))

        values: dict[str, tuple[float, ...]] = {}
        batches: dict[int, _Batch] = {}
        async with self._lock:
            for text in unique:
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    values[text] = cached
                    continue
                batch = self._inflight.get(text)
                if batch is None:
                    batch = self._select_open_batch()
                    if batch is None:
                        batch = _Batch()
                        batch.task = asyncio.create_task(self._run_batch(batch))
                        batch.task.add_done_callback(_consume_task_exception)
                        self._open_batches.append(batch)
                    batch.texts.append(text)
                    self._inflight[text] = batch
                    if len(batch.texts) >= self._max_batch_size:
                        batch.closed = True
                        batch.ready.set()
                batches[id(batch)] = batch

        outcomes = await asyncio.gather(
            *(asyncio.shield(batch.task) for batch in batches.values() if batch.task is not None)
        )
        requests = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        for outcome in outcomes:
            values.update(outcome.vectors)
            requests += outcome.usage.requests
            if outcome.usage.input_tokens is not None:
                input_tokens = (input_tokens or 0) + outcome.usage.input_tokens
            if outcome.usage.output_tokens is not None:
                output_tokens = (output_tokens or 0) + outcome.usage.output_tokens
        return EmbeddingResult(
            vectors=tuple(values[text] for text in requested),
            usage=InferenceUsage(requests=requests, input_tokens=input_tokens, output_tokens=output_tokens),
        )

    def _select_open_batch(self) -> _Batch | None:
        for batch in reversed(self._open_batches):
            if not batch.closed and len(batch.texts) < self._max_batch_size:
                return batch
        return None

    async def _run_batch(self, batch: _Batch) -> _BatchOutcome:
        try:
            if not batch.closed:
                with suppress(TimeoutError):
                    await asyncio.wait_for(batch.ready.wait(), timeout=self._coalesce_seconds)
            async with self._lock:
                batch.closed = True
            result = await self._model.embed(tuple(batch.texts))
            vectors = tuple(result.vectors)
            if len(vectors) != len(batch.texts):
                raise ValueError("embedding vector count does not match batch size")  # noqa: TRY003, TRY301
            outcome = _BatchOutcome(
                vectors=dict(zip(batch.texts, vectors, strict=True)),
                usage=result.usage,
            )
            async with self._lock:
                if self._cache_size > 0:
                    for text, vector in outcome.vectors.items():
                        self._cache[text] = vector
                        self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                self._forget(batch)
            return outcome  # noqa: TRY300
        except BaseException:
            async with self._lock:
                self._forget(batch)
            raise

    def _forget(self, batch: _Batch) -> None:
        for text in batch.texts:
            if self._inflight.get(text) is batch:
                del self._inflight[text]
        with suppress(ValueError):
            self._open_batches.remove(batch)


def _consume_task_exception(task: asyncio.Task[_BatchOutcome]) -> None:
    if not task.cancelled():
        task.exception()


__all__ = ["CoalescingEmbeddingModel"]
