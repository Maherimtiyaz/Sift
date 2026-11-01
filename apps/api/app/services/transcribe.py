import asyncio
import os
import tempfile

_whisper = None


def _transcribe_sync(path: str) -> str:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel  # imported lazily: heavy, and not needed by tests

        _whisper = WhisperModel(os.getenv("WHISPER_MODEL", "small"), compute_type="int8")
    segments, _ = _whisper.transcribe(path, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


async def transcribe(data: bytes, suffix: str = ".webm") -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        return await asyncio.to_thread(_transcribe_sync, f.name)
