"""Chat-completion providers behind one small interface (think: a Java interface with
OpenAI, Azure and mock implementations, chosen by configuration)."""

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openai import AsyncAzureOpenAI, AsyncOpenAI


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class ChatModel(Protocol):
    @property
    def name(self) -> str: ...

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Yield the assistant reply as text deltas."""
        ...


class OpenAIChatModel:
    """Works for both OpenAI and Azure OpenAI (for Azure, `model` is the deployment name)."""

    def __init__(
        self, client: AsyncOpenAI | AsyncAzureOpenAI, model: str, temperature: float
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    @property
    def name(self) -> str:
        return self._model

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        payload: Any = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self._model, messages=payload, temperature=self._temperature, stream=True
        )
        async for chunk in response:
            if chunk.choices and (delta := chunk.choices[0].delta.content):
                yield delta


_SOURCE_RE = re.compile(r'<source id="(\d+)" title="([^"]*)"[^>]*>\n?(.*?)\n?</source>', re.S)


class MockChatModel:
    """Deterministic stand-in for local development and tests: no API key, no network.

    It quotes the first sentences of the best-ranked source, so the whole RAG flow
    (retrieval, citations, streaming, persistence) can be exercised end-to-end.
    """

    def __init__(self, delay_seconds: float = 0.01) -> None:
        self._delay = delay_seconds

    @property
    def name(self) -> str:
        return "mock"

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for word in self._compose(messages).split(" "):
            yield word + " "
            if self._delay:
                await asyncio.sleep(self._delay)

    @staticmethod
    def _compose(messages: list[ChatMessage]) -> str:
        sources = [m for msg in messages for m in _SOURCE_RE.finditer(msg.content)]
        if not sources:
            return "I couldn't find anything about that in the knowledge base."
        source_id, title, body = sources[0].groups()
        text = " ".join(
            line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")
        )
        sentences = re.split(r"(?<=[.!?])\s+", text)
        excerpt = " ".join(sentences[:2]).strip()
        return (
            f"According to **{title}** [{source_id}]: {excerpt}\n\n"
            "_(Mock LLM response. Set LLM_PROVIDER to use a real model.)_"
        )
