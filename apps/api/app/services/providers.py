import os


class ProviderConfigurationError(ValueError):
    """An AI provider setting is invalid or missing a required credential."""


DEMO_TRANSCRIPT = (
    "Finish the demo checklist, schedule a 30-minute project review tomorrow at 3pm, "
    "and draft a message to Maya with the project update."
)
DEMO_RESULT = {
    "tasks": [{"text": "Finish the demo checklist", "src": "Finish the demo checklist"}],
    "events": [{
        "title": "Project review",
        "start": "",
        "durationMin": 30,
        "when": "Tomorrow at 3pm",
        "src": "schedule a 30-minute project review tomorrow at 3pm",
    }],
    "messages": [{
        "to": "Maya",
        "body": "Hi Maya, here’s the latest project update.",
        "src": "draft a message to Maya with the project update",
    }],
}


def _provider(name: str, allowed: set[str], default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ProviderConfigurationError(f"{name} must be one of: {choices}.")
    return value


def llm_provider() -> str:
    return _provider("LLM_PROVIDER", {"groq", "anthropic", "ollama", "mock"}, "anthropic")


def transcription_provider() -> str:
    return _provider("TRANSCRIPTION_PROVIDER", {"groq", "local", "mock"}, "local")


def is_demo_mode() -> bool:
    return llm_provider() == "mock" or transcription_provider() == "mock"


def groq_api_key() -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise ProviderConfigurationError("GROQ_API_KEY is required when using a Groq provider.")
    return key
