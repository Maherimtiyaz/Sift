import uuid

from anthropic import APIStatusError

from ..db import Item, Note, User
from .extract import extract
from .providers import ProviderConfigurationError


class SortingFailed(Exception):
    """The configured LLM provider could not sort the transcript."""

    def __init__(self, detail: str):
        super().__init__(detail)


def sorting_failure_detail(error: Exception) -> str:
    generic = "Couldn’t sort your note right now. Try again in a moment."
    if isinstance(error, ProviderConfigurationError):
        return str(error)
    if not isinstance(error, APIStatusError):
        return generic

    body = error.body
    api_error = body.get("error", {}) if isinstance(body, dict) else {}
    message = api_error.get("message", "") if isinstance(api_error, dict) else ""
    if "credit balance is too low" in message.lower():
        return "Claude API credits are exhausted. Add credits in Anthropic Plans & Billing, then try again."
    if error.status_code == 401:
        return "Claude rejected the API key. Check the key in the server’s .env file."
    if error.status_code == 429:
        return "Claude’s usage limit was reached. Check your Anthropic plan and try again later."
    return generic


async def save_note(s, user: User, transcript: str, tz: str) -> Note:
    """Sort a transcript with the configured provider and store it."""
    try:
        sorted_ = await extract(transcript, tz)
    except Exception as e:
        raise SortingFailed(sorting_failure_detail(e)) from e
    note = Note(id=uuid.uuid4(), user_id=user.id, transcript=transcript)
    for kind, key in (("task", "tasks"), ("event", "events"), ("message", "messages")):
        # events remember the timezone they were spoken in, so Google gets the right local time
        note.items += [Item(kind=kind, data={**d, **({"tz": tz} if kind == "event" else {})})
                       for d in sorted_.get(key, [])]
    s.add(note)
    await s.commit()
    return note
