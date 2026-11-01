import asyncio
import os
import threading
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

SAMPLE_RATE = 16_000
BYTES_PER_SEC = SAMPLE_RATE * 2  # 16-bit mono PCM


@dataclass(frozen=True)
class Seg:
    start: float  # seconds from the start of the audio that was transcribed
    end: float
    text: str


Runner = Callable[[np.ndarray, str], Sequence[Seg]]  # (float32 audio, prompt) -> segments, blocking

_model = None
_lock = threading.Lock()  # one inference at a time across all live sessions


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # lazy: heavy, and tests never need it

        _model = WhisperModel(os.getenv("WHISPER_LIVE_MODEL", "base"), compute_type="int8")
    return _model


def preload() -> None:
    with _lock:
        _load()


def make_runner() -> Runner:
    language = os.getenv("WHISPER_LANGUAGE") or None  # None = auto-detect

    def run(audio: np.ndarray, prompt: str) -> list[Seg]:
        with _lock:
            segments, _ = _load().transcribe(
                audio, language=language, vad_filter=True,
                initial_prompt=prompt or None, condition_on_previous_text=False)
            return [Seg(s.start, s.end, s.text) for s in segments]

    return run


class LiveTranscriber:
    """Turns streamed PCM into text that is final once it has settled, plus a tail that may still change.

    Each step transcribes only the audio after the last committed boundary. Segments that ended at least
    `stable_gap` seconds before the end of the buffer are committed and cut off, so the work per step stays
    small however long you talk.
    """

    def __init__(self, run: Runner, stable_gap: float = 1.0, max_window: float = 25.0):
        self.run, self.stable_gap, self.max_window = run, stable_gap, max_window
        self.buf = bytearray()
        self.committed: list[str] = []
        self.lock = asyncio.Lock()

    def feed(self, pcm: bytes) -> None:
        self.buf += pcm

    @property
    def text(self) -> str:
        return " ".join(self.committed).strip()

    async def step(self, final: bool = False) -> str:
        """Transcribe the uncommitted audio. Returns the unsettled tail; settled text is in `self.text`."""
        async with self.lock:
            snap = bytes(self.buf)  # a prefix of the buffer, which keeps growing while we work
            if not snap or (len(snap) < BYTES_PER_SEC // 2 and not final):
                return ""
            audio = np.frombuffer(snap, dtype=np.int16).astype(np.float32) / 32768.0
            segs = [s for s in await asyncio.to_thread(self.run, audio, self.text[-200:]) if s.text.strip()]
            dur = len(audio) / SAMPLE_RATE
            # nothing settles during one long breathless stretch, so past max_window commit everything
            gap = 0.0 if final or dur > self.max_window else self.stable_gap
            n = 0
            for s in segs:
                if s.end <= dur - gap + 0.05:
                    n += 1
                else:
                    break
            self.committed += [s.text.strip() for s in segs[:n]]
            if n:
                del self.buf[: min(int(segs[n - 1].end * SAMPLE_RATE) * 2, len(snap))]
            return " ".join(s.text.strip() for s in segs[n:])
