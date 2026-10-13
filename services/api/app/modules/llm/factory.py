from functools import lru_cache

from openai import AsyncAzureOpenAI, AsyncOpenAI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.modules.llm.chat import ChatModel, MockChatModel, OpenAIChatModel
from app.modules.llm.embeddings import Embedder, MockEmbedder, OpenAIEmbedder


def _secret(value: SecretStr | None) -> str:
    return value.get_secret_value().strip() if value else ""


def _client(settings: Settings) -> AsyncOpenAI | AsyncAzureOpenAI:
    if settings.llm_provider == "azure_openai":
        api_key = _secret(settings.azure_openai_api_key)
        if not (settings.azure_openai_endpoint and api_key):
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required")
        return AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=api_key,
            api_version=settings.azure_openai_api_version,
        )
    api_key = _secret(settings.openai_api_key)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
    return AsyncOpenAI(api_key=api_key, base_url=settings.openai_base_url or None)


@lru_cache
def get_chat_model() -> ChatModel:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockChatModel()
    model = (
        settings.azure_openai_chat_deployment
        if settings.llm_provider == "azure_openai"
        else settings.openai_chat_model
    )
    if not model:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is required")
    return OpenAIChatModel(_client(settings), model, settings.llm_temperature)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockEmbedder()
    model = (
        settings.azure_openai_embedding_deployment
        if settings.llm_provider == "azure_openai"
        else settings.openai_embedding_model
    )
    if not model:
        raise RuntimeError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is required")
    return OpenAIEmbedder(_client(settings), model)
