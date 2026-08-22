"""Unit tests for provider modules."""

import json
from unittest.mock import MagicMock, patch

import providers.embeddings as embeddings
import providers.llm as llm_provider
import providers.supabase_client as supabase_provider
import providers.vision as vision_provider


def test_embed_text_returns_zero_vector_for_blank_input():
    assert embeddings.embed_text("") == [0.0] * 384
    assert embeddings.embed_text("   ") == [0.0] * 384


@patch("providers.embeddings.get_supabase")
def test_embed_text_parses_byte_response(get_supabase_mock):
    sb = MagicMock()
    sb.functions.invoke.return_value = json.dumps({"embedding": [1.0] * 384}).encode()
    get_supabase_mock.return_value = sb

    result = embeddings.embed_text("kaffee")

    sb.functions.invoke.assert_called_once_with(
        "generate-embedding",
        invoke_options={"body": {"text": "kaffee"}},
    )
    assert result == [1.0] * 384


@patch("providers.embeddings.get_supabase")
def test_embed_text_returns_embedding_from_dict_response(get_supabase_mock):
    sb = MagicMock()
    sb.functions.invoke.return_value = {"embedding": [0.5] * 384}
    get_supabase_mock.return_value = sb

    result = embeddings.embed_text("tee")

    assert result == [0.5] * 384


@patch("providers.embeddings.get_supabase")
def test_embed_text_returns_zero_vector_for_invalid_length(get_supabase_mock):
    sb = MagicMock()
    sb.functions.invoke.return_value = {"embedding": [1.0, 2.0]}
    get_supabase_mock.return_value = sb

    assert embeddings.embed_text("kaffee") == [0.0] * 384


@patch("providers.embeddings.get_supabase", side_effect=RuntimeError("boom"))
def test_embed_text_returns_zero_vector_on_error(_get_supabase_mock):
    assert embeddings.embed_text("kaffee") == [0.0] * 384


@patch("providers.embeddings.embed_text", side_effect=[[1.0] * 384, [2.0] * 384])
def test_embed_batch_calls_embed_text_for_each_item(embed_text_mock):
    result = embeddings.embed_batch(["a", "b"])

    assert result == [[1.0] * 384, [2.0] * 384]
    assert [call.args[0] for call in embed_text_mock.call_args_list] == ["a", "b"]


@patch("providers.llm.ChatOpenAI")
def test_get_llm_builds_cached_chat_client(chat_openai_mock):
    llm_provider.get_llm.cache_clear()
    client = object()
    chat_openai_mock.return_value = client

    first = llm_provider.get_llm()
    second = llm_provider.get_llm()

    chat_openai_mock.assert_called_once_with(
        model=llm_provider.config.TEXT_MODEL,
        openai_api_key=llm_provider.config.GEMINI_API_KEY,
        openai_api_base=llm_provider.config.GEMINI_BASE_URL,
        temperature=0.1,
        max_tokens=16384,
    )
    assert first is client
    assert second is client


@patch("providers.llm.ChatOpenAI")
def test_get_llm_cache_key_includes_temperature(chat_openai_mock):
    llm_provider.get_llm.cache_clear()
    chat_openai_mock.side_effect = [object(), object()]

    first = llm_provider.get_llm(temperature=0.1)
    second = llm_provider.get_llm(temperature=0.3)

    assert chat_openai_mock.call_count == 2
    assert first is not second


@patch("providers.supabase_client.create_client")
def test_get_supabase_builds_cached_client(create_client_mock):
    supabase_provider.get_supabase.cache_clear()
    client = object()
    create_client_mock.return_value = client

    first = supabase_provider.get_supabase()
    second = supabase_provider.get_supabase()

    create_client_mock.assert_called_once_with(
        supabase_provider.config.SUPABASE_URL,
        supabase_provider.config.SUPABASE_SERVICE_ROLE_KEY,
    )
    assert first is client
    assert second is client


@patch("providers.vision.AsyncOpenAI")
def test_get_vision_client_builds_cached_client(async_openai_mock):
    vision_provider.get_vision_client.cache_clear()
    client = object()
    async_openai_mock.return_value = client

    first = vision_provider.get_vision_client()
    second = vision_provider.get_vision_client()

    async_openai_mock.assert_called_once_with(
        api_key=vision_provider.config.GEMINI_API_KEY,
        base_url=vision_provider.config.GEMINI_BASE_URL,
    )
    assert first is client
    assert second is client
