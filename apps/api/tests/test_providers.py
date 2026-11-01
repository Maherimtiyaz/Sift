import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.routers.notes import create_note
from app.services.extract import extract
from app.services.providers import (
    DEMO_RESULT,
    DEMO_TRANSCRIPT,
    ProviderConfigurationError,
    is_demo_mode,
    llm_provider,
    transcription_provider,
)
from app.services.transcribe import transcribe


def test_provider_defaults_and_demo_switch(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    assert llm_provider() == "anthropic"
    assert transcription_provider() == "local"
    assert not is_demo_mode()

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert is_demo_mode()


@pytest.mark.parametrize(("name", "value"), [
    ("LLM_PROVIDER", "unknown"),
    ("TRANSCRIPTION_PROVIDER", "anthropic"),
])
def test_invalid_provider_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ProviderConfigurationError, match=name):
        (llm_provider if name == "LLM_PROVIDER" else transcription_provider)()


def test_demo_extraction_uses_fixed_output_without_an_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "groq")
    result = asyncio.run(extract("a private note that must be ignored", "UTC"))
    assert result == DEMO_RESULT
    assert result is not DEMO_RESULT


def test_demo_note_route_discards_user_input(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "groq")
    captured = {}

    async def save(_session, _user, transcript, _tz):
        captured["transcript"] = transcript
        return SimpleNamespace(
            id=uuid.uuid4(),
            transcript=transcript,
            created_at=datetime.now(timezone.utc),
            items=[],
        )

    monkeypatch.setattr("app.routers.notes.save_note", save)
    result = asyncio.run(create_note(
        audio=None,
        text="private note contents",
        tz="UTC",
        user=object(),
        s=object(),
    ))
    assert captured["transcript"] == DEMO_TRANSCRIPT
    assert result["transcript"] == DEMO_TRANSCRIPT


def test_groq_extraction_sends_structured_request(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    body = {"choices": [{"message": {"content": json.dumps(DEMO_RESULT)}}]}

    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json=body)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.extract.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert asyncio.run(extract("Finish the checklist", "UTC")) == DEMO_RESULT


def test_groq_transcription_uploads_audio(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert "whisper-large-v3" in request.content.decode()
        assert "sample audio bytes" in request.content.decode()
        return httpx.Response(200, json={"text": "Transcribed sample"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.transcribe.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert asyncio.run(transcribe(b"sample audio bytes", ".webm")) == "Transcribed sample"


def test_mock_transcription_returns_fixed_sample_without_an_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "mock")
    assert asyncio.run(transcribe(b"private audio")) == DEMO_TRANSCRIPT
