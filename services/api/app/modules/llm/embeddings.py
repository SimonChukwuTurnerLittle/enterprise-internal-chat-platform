import hashlib
import math
import re
from typing import Protocol

from openai import AsyncAzureOpenAI, AsyncOpenAI

EMBEDDING_DIMENSIONS = 1536  # must match the vector(...) column in the migrations


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """OpenAI / Azure OpenAI embeddings (for Azure, `model` is the deployment name)."""

    def __init__(
        self,
        client: AsyncOpenAI | AsyncAzureOpenAI,
        model: str,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = 64,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = await self._client.embeddings.create(
                model=self._model, input=batch, dimensions=self._dimensions
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its me my "
    "of on or our so that the their them this to was we what when where which who why "
    "will with you your".split()
)


class MockEmbedder:
    """Deterministic bag-of-words embedding via feature hashing.

    Cosine similarity then approximates keyword overlap, which is enough for retrieval in
    local development and tests without an API key. Not semantic: synonyms will not match.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            token = _stem(token)
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % self._dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0  # avoid a zero vector (cosine distance is undefined for it)
            return vector
        return [v / norm for v in vector]


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token
