import asyncio
import mimetypes
import os
import tempfile

import httpx

from .providers import (
    DEMO_TRANSCRIPT,
    ProviderConfigurationError,
    groq_api_key,
    is_demo_mode,
    transcription_provider,
)

_whisper = None


def _transcribe_sync(path: str) -> str:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel  # imported lazily: heavy, and not needed by tests

        _whisper = WhisperModel(os.getenv("WHISPER_MODEL", "small"), compute_type="int8")
    segments, _ = _whisper.transcribe(path, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


async def transcribe(data: bytes, suffix: str = ".webm") -> str:
    if is_demo_mode():
        return DEMO_TRANSCRIPT

    provider = transcription_provider()
    if provider == "mock":
        return DEMO_TRANSCRIPT
    if provider == "groq":
        api_key = groq_api_key()
        media_type = mimetypes.guess_type("audio" + suffix)[0] or "application/octet-stream"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")},
                files={"file": ("audio" + suffix, data, media_type)},
            )
        response.raise_for_status()
        text = response.json().get("text", "").strip()
        if not text:
            raise ValueError("The Groq transcription provider returned no text.")
        return text
    if provider != "local":
        raise ProviderConfigurationError(f"Unsupported TRANSCRIPTION_PROVIDER: {provider}.")

    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        return await asyncio.to_thread(_transcribe_sync, f.name)
